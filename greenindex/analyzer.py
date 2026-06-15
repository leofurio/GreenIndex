"""Scansione del repository e rilevamento delle violazioni.

L'analizzatore cammina nell'albero del repository, rileva il linguaggio di
ogni file ed esegue tre famiglie di rilevatori:

* rilevatori basati su regex (riga per riga, sul sorgente senza commenti);
* rilevatori basati su AST per Python (alta precisione);
* uno scanner strutturale di cicli annidati per i linguaggi C-like;
* scansioni a livello di repository (dipendenze, asset binari, Dockerfile).
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .rules import DEFAULT_RULES, Rule, Violation, rules_by_id
from .textutils import (
    C_LIKE,
    CODE_LANGUAGES,
    count_code_lines,
    detect_language,
    mask_code,
    strip_comments,
)

# Directory che non vanno mai analizzate.
DEFAULT_IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components",
    "venv", ".venv", "env", ".env", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", "out",
    ".next", ".nuxt", "target", "vendor", ".idea", ".vscode",
    "coverage", ".gradle", "Pods", ".terraform", "site-packages",
}

# Estensioni di asset binari considerate dalla regola GC070.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".ico", ".psd"}
MEDIA_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav", ".zip", ".tar", ".gz"}

# Soglie per gli asset (in byte).
IMAGE_SIZE_LIMIT = 500 * 1024       # 500 KB
MEDIA_SIZE_LIMIT = 2 * 1024 * 1024  # 2 MB

# Limite di dimensione dei file di testo analizzati (evita file generati enormi).
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024

# Dipendenze considerate "pesanti" e relativa nota.
HEAVY_DEPENDENCIES = {
    "tensorflow": "framework ML molto grande (centinaia di MB)",
    "torch": "framework ML molto grande",
    "pytorch": "framework ML molto grande",
    "selenium": "avvia un browser completo: alto consumo di RAM/CPU",
    "puppeteer": "scarica ed esegue Chromium (centinaia di MB)",
    "playwright": "scarica più browser completi",
    "electron": "include un intero runtime Chromium",
    "moment": "libreria date pesante; preferisci date-fns/Luxon o l'API nativa",
    "pandas": "potente ma con footprint di memoria elevato per usi semplici",
    "scipy": "libreria scientifica di grandi dimensioni",
    "opencv-python": "libreria di computer vision di grandi dimensioni",
    "lodash": "spesso sostituibile con metodi nativi di Array/Object",
}


@dataclass
class FileStat:
    path: str
    language: Optional[str]
    code_lines: int
    bytes: int


@dataclass
class AnalysisResult:
    """Risultato dell'analisi di un repository."""

    root: str
    violations: List[Violation] = field(default_factory=list)
    files: List[FileStat] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=lambda: list(DEFAULT_RULES))
    errors: List[str] = field(default_factory=list)

    # --- statistiche aggregate ------------------------------------------- #
    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def code_files(self) -> int:
        return sum(1 for f in self.files if f.language in CODE_LANGUAGES)

    @property
    def total_code_lines(self) -> int:
        return sum(f.code_lines for f in self.files if f.language in CODE_LANGUAGES)

    @property
    def language_breakdown(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.files:
            if f.language:
                out[f.language] = out.get(f.language, 0) + f.code_lines
        return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


# --------------------------------------------------------------------------- #
# Rilevatore AST per Python.
# --------------------------------------------------------------------------- #
class _PythonAstDetector(ast.NodeVisitor):
    """Rileva anti-pattern Python tramite analisi dell'AST."""

    # Nomi di moduli/funzioni che indicano una chiamata di rete.
    NETWORK_CALLERS = {"requests", "httpx", "urllib", "urllib2", "aiohttp", "http"}
    NETWORK_METHODS = {"get", "post", "put", "delete", "patch", "head", "request", "urlopen"}
    # Indizi di query al database (ORM o driver).
    QUERY_METHODS = {
        "execute", "executemany", "query", "filter", "filter_by", "get",
        "first", "all", "fetchone", "fetchall", "find", "find_one", "aggregate",
    }
    QUERY_ATTR_HINTS = {"objects", "session", "cursor", "db", "query"}

    def __init__(self, path: str, enabled: set):
        self.path = path
        self.enabled = enabled
        self.violations: List[Violation] = []
        self._loop_depth = 0

    # -- helper ----------------------------------------------------------- #
    def _add(self, rule_id: str, node: ast.AST, message: str) -> None:
        if rule_id not in self.enabled:
            return
        self.violations.append(
            Violation(
                rule_id=rule_id,
                path=self.path,
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0),
                message=message,
            )
        )

    @staticmethod
    def _call_name(node: ast.Call) -> Tuple[str, str]:
        """Restituisce (root, attr) per una chiamata, es. requests.get -> (requests, get)."""
        func = node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            value = func.value
            if isinstance(value, ast.Name):
                return value.id, attr
            if isinstance(value, ast.Attribute):
                return value.attr, attr
            return "", attr
        if isinstance(func, ast.Name):
            return "", func.id
        return "", ""

    # -- visita dei cicli ------------------------------------------------- #
    def _visit_loop(self, node: ast.AST) -> None:
        if self._loop_depth >= 1:
            self._add(
                "GC001", node,
                "Ciclo annidato dentro un altro ciclo (complessità ≥ O(n²)).",
            )
        # Busy-wait: while True con time.sleep al suo interno.
        if isinstance(node, ast.While) and self._is_true_constant(node.test):
            if self._contains_sleep(node):
                self._add(
                    "GC003", node,
                    "Ciclo 'while True' con sleep: polling attivo della CPU.",
                )
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    visit_For = _visit_loop
    visit_AsyncFor = _visit_loop
    visit_While = _visit_loop

    @staticmethod
    def _is_true_constant(test: ast.AST) -> bool:
        return isinstance(test, ast.Constant) and test.value is True

    @staticmethod
    def _contains_sleep(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr == "sleep":
                    return True
        return False

    # -- chiamate dentro i cicli ----------------------------------------- #
    def visit_Call(self, node: ast.Call) -> None:
        root, attr = self._call_name(node)

        # Lettura intero file (gestita anche via regex per altri linguaggi,
        # qui solo come supporto: la regola GC010 resta principalmente regex).
        if self._loop_depth > 0:
            # Chiamata di rete dentro un ciclo.
            if (root in self.NETWORK_CALLERS and attr in self.NETWORK_METHODS) or attr == "urlopen":
                self._add(
                    "GC020", node,
                    f"Chiamata di rete '{root + '.' if root else ''}{attr}' dentro un ciclo.",
                )
            # Query al DB dentro un ciclo (N+1).
            elif attr in self.QUERY_METHODS and (root in self.QUERY_ATTR_HINTS or root == ""):
                # Riduce i falsi positivi: 'get'/'all' generici senza contesto DB
                # vengono ignorati se non c'è un indizio di accesso ai dati.
                if attr in {"execute", "executemany", "fetchone", "fetchall"} or root in self.QUERY_ATTR_HINTS:
                    self._add(
                        "GC021", node,
                        f"Possibile query al DB ('{attr}') dentro un ciclo: pattern N+1.",
                    )

        self.generic_visit(node)

    # -- concatenazione di stringhe in un ciclo --------------------------- #
    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._loop_depth > 0 and isinstance(node.op, ast.Add):
            if self._looks_like_string(node.value):
                self._add(
                    "GC002", node,
                    "Concatenazione di stringhe con += dentro un ciclo.",
                )
        self.generic_visit(node)

    @staticmethod
    def _looks_like_string(value: ast.AST) -> bool:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return True
        if isinstance(value, ast.JoinedStr):  # f-string
            return True
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            return _PythonAstDetector._looks_like_string(value.left) or _PythonAstDetector._looks_like_string(value.right)
        return False

    # -- file aperti senza context manager -------------------------------- #
    def visit_With(self, node: ast.With) -> None:
        # Le open() usate qui come context manager sono "buone": le saltiamo
        # marcandole, poi visitiamo il resto.
        for item in node.items:
            self._mark_safe_open(item.context_expr)
        self.generic_visit(node)

    visit_AsyncWith = visit_With  # type: ignore[assignment]

    def _mark_safe_open(self, expr: ast.AST) -> None:
        if isinstance(expr, ast.Call):
            setattr(expr, "_gi_safe_open", True)

    def generic_visit(self, node: ast.AST) -> None:  # noqa: D401
        # Rileva open() non gestite da 'with'.
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open" and not getattr(node, "_gi_safe_open", False):
                self._add(
                    "GC011", node,
                    "open() senza 'with': la risorsa file potrebbe non essere chiusa.",
                )
        super().generic_visit(node)


# --------------------------------------------------------------------------- #
# Scanner di cicli annidati per linguaggi C-like.
# --------------------------------------------------------------------------- #
_CLIKE_LOOP_RE = re.compile(r"\b(for|while|foreach)\b")


def detect_nested_loops_clike(masked: str) -> List[int]:
    """Trova i numeri di riga in cui un ciclo è annidato in un altro.

    Lavora sul sorgente "mascherato" (senza stringhe/commenti) usando un
    semplice automa basato sul conteggio delle parentesi graffe.
    """
    lines: List[int] = []
    stack: List[bool] = []  # per ogni blocco {}: True se è il corpo di un ciclo
    pending_loop = False     # abbiamo visto una keyword di ciclo in attesa del '{'
    paren_depth = 0
    i = 0
    n = len(masked)
    line_no = 1

    # Pre-individua le posizioni delle keyword di ciclo.
    loop_positions = {m.start() for m in _CLIKE_LOOP_RE.finditer(masked)}

    while i < n:
        ch = masked[i]
        if ch == "\n":
            line_no += 1
            i += 1
            continue
        if i in loop_positions:
            pending_loop = True
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            if paren_depth > 0:
                paren_depth -= 1
        elif ch == "{":
            is_loop_body = pending_loop and paren_depth == 0
            if is_loop_body and any(stack):
                lines.append(line_no)
            stack.append(is_loop_body)
            pending_loop = False
        elif ch == "}":
            if stack:
                stack.pop()
        elif ch == ";" and paren_depth == 0:
            # Fine istruzione: una keyword di ciclo senza blocco viene scartata.
            pending_loop = False
        i += 1

    return lines


# --------------------------------------------------------------------------- #
# Analyzer principale.
# --------------------------------------------------------------------------- #
class Analyzer:
    """Analizza un repository applicando un insieme di regole."""

    def __init__(self, rules: Optional[List[Rule]] = None,
                 ignored_dirs: Optional[set] = None):
        self.rules = list(rules) if rules is not None else list(DEFAULT_RULES)
        self.rules_by_id = rules_by_id(self.rules)
        self.enabled_ids = set(self.rules_by_id)
        self.ignored_dirs = ignored_dirs or set(DEFAULT_IGNORED_DIRS)

        # Pre-compila i pattern delle regole regex.
        self._compiled: Dict[str, re.Pattern] = {}
        self._absent: Dict[str, re.Pattern] = {}
        for rule in self.rules:
            if rule.detector in ("regex", "dockerfile") and rule.pattern:
                self._compiled[rule.id] = re.compile(rule.pattern, rule.flags)
            if rule.require_absent:
                self._absent[rule.id] = re.compile(rule.require_absent, rule.flags)

    # ------------------------------------------------------------------ #
    def analyze(self, root: str) -> AnalysisResult:
        root = os.path.abspath(root)
        result = AnalysisResult(root=root, rules=self.rules)
        if not os.path.exists(root):
            result.errors.append(f"Percorso inesistente: {root}")
            return result

        if os.path.isfile(root):
            self._analyze_one_file(root, os.path.dirname(root) or ".", result)
            self._scan_dependencies(os.path.dirname(root) or ".", result)
            return result

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.ignored_dirs and not d.startswith(".")]
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                self._analyze_one_file(fpath, root, result)

        self._scan_dependencies(root, result)
        return result

    # ------------------------------------------------------------------ #
    def _rel(self, path: str, root: str) -> str:
        try:
            return os.path.relpath(path, root)
        except ValueError:
            return path

    def _analyze_one_file(self, fpath: str, root: str, result: AnalysisResult) -> None:
        rel = self._rel(fpath, root)
        try:
            size = os.path.getsize(fpath)
        except OSError as exc:
            result.errors.append(f"{rel}: {exc}")
            return

        ext = os.path.splitext(fpath)[1].lower()
        language = detect_language(fpath)

        # Asset binari -> regola GC070.
        if ext in IMAGE_EXTS or ext in MEDIA_EXTS:
            self._check_asset(fpath, rel, ext, size, result)
            result.files.append(FileStat(path=rel, language=None, code_lines=0, bytes=size))
            return

        # File di testo troppo grandi: registra le statistiche ma non analizza.
        if size > MAX_TEXT_FILE_BYTES:
            result.files.append(FileStat(path=rel, language=language, code_lines=0, bytes=size))
            return

        try:
            with open(fpath, "r", encoding="utf-8", errors="strict") as fh:
                source = fh.read()
        except (UnicodeDecodeError, OSError):
            # File binario o non leggibile: ignorato dall'analisi testuale.
            result.files.append(FileStat(path=rel, language=language, code_lines=0, bytes=size))
            return

        code_lines = count_code_lines(source)
        result.files.append(FileStat(path=rel, language=language, code_lines=code_lines, bytes=size))

        # Dockerfile: analisi dedicata.
        if language == "dockerfile":
            self._check_dockerfile(rel, source, result)

        # Regole regex (sul sorgente senza commenti).
        self._apply_regex_rules(rel, source, language, result)

        # Cicli annidati.
        self._check_nested_loops(rel, source, language, result)

        # Rilevatori AST per Python.
        if language == "python":
            self._apply_python_ast(rel, source, result)

    # ------------------------------------------------------------------ #
    def _apply_regex_rules(self, rel: str, source: str, language: Optional[str],
                           result: AnalysisResult) -> None:
        # I file di tipo sconosciuto (binari, docs senza estensione nota) non
        # vengono scanditi dalle regole regex per evitare falsi positivi.
        if language is None:
            return
        cleaned = strip_comments(source, language)
        cleaned_lines = cleaned.splitlines()
        original_lines = source.splitlines()

        for rule in self.rules:
            if rule.detector != "regex" or rule.id not in self._compiled:
                continue
            if rule.languages and language not in rule.languages:
                continue
            pattern = self._compiled[rule.id]
            absent = self._absent.get(rule.id)
            for idx, line in enumerate(cleaned_lines):
                m = pattern.search(line)
                if not m:
                    continue
                if absent and absent.search(line):
                    continue
                snippet = original_lines[idx].strip() if idx < len(original_lines) else line.strip()
                result.violations.append(
                    Violation(
                        rule_id=rule.id,
                        path=rel,
                        line=idx + 1,
                        column=m.start() + 1,
                        snippet=snippet[:200],
                        message=rule.name,
                    )
                )

    # ------------------------------------------------------------------ #
    def _check_nested_loops(self, rel: str, source: str, language: Optional[str],
                            result: AnalysisResult) -> None:
        if "GC001" not in self.enabled_ids:
            return
        # Python è gestito dall'AST; qui solo i linguaggi C-like.
        if language not in C_LIKE:
            return
        masked = mask_code(source, language)
        original_lines = source.splitlines()
        for line_no in detect_nested_loops_clike(masked):
            snippet = original_lines[line_no - 1].strip() if 0 < line_no <= len(original_lines) else ""
            result.violations.append(
                Violation(
                    rule_id="GC001",
                    path=rel,
                    line=line_no,
                    snippet=snippet[:200],
                    message="Ciclo annidato dentro un altro ciclo.",
                )
            )

    # ------------------------------------------------------------------ #
    def _apply_python_ast(self, rel: str, source: str, result: AnalysisResult) -> None:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            result.errors.append(f"{rel}: errore di sintassi Python ({exc.msg})")
            return
        detector = _PythonAstDetector(rel, self.enabled_ids)
        detector.visit(tree)
        # Aggiunge lo snippet alle violazioni AST.
        lines = source.splitlines()
        for v in detector.violations:
            if 0 < v.line <= len(lines):
                v.snippet = lines[v.line - 1].strip()[:200]
        result.violations.extend(detector.violations)

    # ------------------------------------------------------------------ #
    def _check_dockerfile(self, rel: str, source: str, result: AnalysisResult) -> None:
        lines = source.splitlines()
        from_lines = []
        has_stage_alias = False
        for idx, raw in enumerate(lines):
            line = raw.strip()
            if line.upper().startswith("FROM "):
                from_lines.append((idx + 1, line))
                if re.search(r"\bAS\b", line, re.IGNORECASE):
                    has_stage_alias = True
                # GC080: tag :latest oppure tag assente.
                if "GC080" in self.enabled_ids:
                    image = line.split()[1] if len(line.split()) > 1 else ""
                    tag_part = image.split("/")[-1]
                    if ":latest" in image or ":" not in tag_part:
                        result.violations.append(
                            Violation(
                                rule_id="GC080",
                                path=rel,
                                line=idx + 1,
                                snippet=line[:200],
                                message="Immagine base senza tag fissato (:latest).",
                            )
                        )
        # GC081: nessuna multi-stage build su base "pesante".
        if "GC081" in self.enabled_ids and from_lines and not has_stage_alias:
            heavy_base = re.compile(r"\b(node|python|golang|maven|gradle|openjdk|rust|ruby)\b", re.IGNORECASE)
            if any(heavy_base.search(l) for _, l in from_lines):
                line_no, line = from_lines[0]
                result.violations.append(
                    Violation(
                        rule_id="GC081",
                        path=rel,
                        line=line_no,
                        snippet=line[:200],
                        message="Dockerfile senza multi-stage build su immagine di build pesante.",
                    )
                )

    # ------------------------------------------------------------------ #
    def _check_asset(self, fpath: str, rel: str, ext: str, size: int,
                     result: AnalysisResult) -> None:
        if "GC070" not in self.enabled_ids:
            return
        limit = IMAGE_SIZE_LIMIT if ext in IMAGE_EXTS else MEDIA_SIZE_LIMIT
        if size > limit:
            result.violations.append(
                Violation(
                    rule_id="GC070",
                    path=rel,
                    line=0,
                    snippet=f"{ext} • {_human_size(size)}",
                    message=f"Asset di {_human_size(size)} (soglia {_human_size(limit)}).",
                    extra={"bytes": str(size)},
                )
            )

    # ------------------------------------------------------------------ #
    def _scan_dependencies(self, root: str, result: AnalysisResult) -> None:
        if "GC051" not in self.enabled_ids:
            return
        # requirements*.txt
        for fname in os.listdir(root) if os.path.isdir(root) else []:
            low = fname.lower()
            fpath = os.path.join(root, fname)
            if not os.path.isfile(fpath):
                continue
            if low.startswith("requirements") and low.endswith(".txt"):
                self._scan_requirements(fpath, self._rel(fpath, root), result)
            elif low == "package.json":
                self._scan_package_json(fpath, self._rel(fpath, root), result)

    def _scan_requirements(self, fpath: str, rel: str, result: AnalysisResult) -> None:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return
        for idx, line in enumerate(lines):
            name = re.split(r"[=<>!~\[ ;#]", line.strip(), 1)[0].strip().lower()
            if name in HEAVY_DEPENDENCIES:
                result.violations.append(
                    Violation(
                        rule_id="GC051",
                        path=rel,
                        line=idx + 1,
                        snippet=line.strip()[:200],
                        message=f"Dipendenza pesante '{name}': {HEAVY_DEPENDENCIES[name]}.",
                    )
                )

    def _scan_package_json(self, fpath: str, rel: str, result: AnalysisResult) -> None:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            return
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            m = re.match(r'\s*"([^"]+)"\s*:', line)
            if not m:
                continue
            name = m.group(1).lower()
            if name in HEAVY_DEPENDENCIES:
                result.violations.append(
                    Violation(
                        rule_id="GC051",
                        path=rel,
                        line=idx + 1,
                        snippet=line.strip()[:200],
                        message=f"Dipendenza pesante '{name}': {HEAVY_DEPENDENCIES[name]}.",
                    )
                )


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
