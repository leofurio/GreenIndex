"""Utility di testo: rilevamento del linguaggio e pulizia del sorgente.

Per ridurre i falsi positivi gli analizzatori non lavorano sul sorgente
grezzo ma su versioni "ripulite":

* :func:`strip_comments` rimuove i commenti mantenendo le stringhe (utile per
  le regole che cercano pattern anche dentro le stringhe, es. SQL);
* :func:`mask_code` rimuove sia commenti sia stringhe (utile per l'analisi
  strutturale, es. cicli annidati).

Entrambe preservano il numero di righe (i caratteri rimossi sono sostituiti
con spazi), così le segnalazioni mantengono i numeri di riga corretti.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

# Estensione -> linguaggio canonico.
EXT_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".rs": "rust",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".vue": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "ini",
}

# Linguaggi con sintassi "C-like" (commenti // e /* */, blocchi con graffe).
C_LIKE = {
    "javascript",
    "typescript",
    "java",
    "c",
    "cpp",
    "csharp",
    "go",
    "rust",
    "kotlin",
    "swift",
    "scala",
    "php",
}

# Linguaggi per cui ha senso contare le righe come "codice".
CODE_LANGUAGES = C_LIKE | {"python", "ruby", "sql", "css", "html", "dockerfile"}


def detect_language(path: str) -> Optional[str]:
    """Determina il linguaggio dal nome/estensione del file."""
    name = os.path.basename(path)
    lower = name.lower()
    if lower == "dockerfile" or lower.endswith(".dockerfile") or lower.startswith("dockerfile."):
        return "dockerfile"
    _, ext = os.path.splitext(name)
    return EXT_LANGUAGE.get(ext.lower())


def _scrub(source: str, language: Optional[str], keep_strings: bool) -> str:
    """Sostituisce commenti (ed eventualmente stringhe) con spazi.

    Preserva i caratteri di newline per non alterare la numerazione di riga.
    """
    if not source:
        return source

    is_c_like = language in C_LIKE
    is_python = language == "python"
    is_ruby = language == "ruby"
    is_sql = language == "sql"
    # Linguaggi con commenti '#': python, ruby, yaml, shell, dockerfile.
    hash_comment = language in {"python", "ruby", "yaml", "dockerfile"} or language is None
    # Commenti SQL con '--'.
    dash_comment = is_sql

    out = []
    i = 0
    n = len(source)
    state = "code"  # code | line_comment | block_comment | string
    string_quote = ""
    # Per le triple-quote di Python.
    triple = ""

    def emit(ch: str) -> None:
        # Mantiene i newline, sostituisce il resto con spazio quando si "cancella".
        out.append(ch)

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if state == "code":
            # Inizio commento di riga //.
            if is_c_like and ch == "/" and nxt == "/":
                state = "line_comment"
                emit(" "); emit(" "); i += 2; continue
            # Inizio commento di blocco /* */.
            if is_c_like and ch == "/" and nxt == "*":
                state = "block_comment"
                emit(" "); emit(" "); i += 2; continue
            # Commenti con '#'.
            if hash_comment and ch == "#":
                state = "line_comment"
                emit(" "); i += 1; continue
            # Commenti SQL '--'.
            if dash_comment and ch == "-" and nxt == "-":
                state = "line_comment"
                emit(" "); emit(" "); i += 2; continue
            # Triple-quote Python.
            if is_python and ch in "\"'" and source[i:i + 3] in ('"""', "'''"):
                triple = source[i:i + 3]
                state = "string"
                string_quote = triple
                emit(ch if keep_strings else " ")
                emit(source[i + 1] if keep_strings else " ")
                emit(source[i + 2] if keep_strings else " ")
                i += 3
                continue
            # Stringhe normali.
            if ch in "\"'" or (is_ruby and ch == "`") or (is_c_like and ch == "`"):
                state = "string"
                string_quote = ch
                triple = ""
                emit(ch if keep_strings else " ")
                i += 1
                continue
            emit(ch)
            i += 1
            continue

        if state == "line_comment":
            if ch == "\n":
                state = "code"
                emit("\n")
            else:
                emit(" ")
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                emit(" "); emit(" "); i += 2
            else:
                emit("\n" if ch == "\n" else " ")
                i += 1
            continue

        if state == "string":
            # Escape.
            if ch == "\\" and not triple:
                emit(ch if keep_strings else " ")
                if i + 1 < n:
                    nx = source[i + 1]
                    emit(nx if keep_strings else ("\n" if nx == "\n" else " "))
                i += 2
                continue
            # Fine triple-quote.
            if triple and source[i:i + 3] == triple:
                state = "code"
                emit(source[i] if keep_strings else " ")
                emit(source[i + 1] if keep_strings else " ")
                emit(source[i + 2] if keep_strings else " ")
                i += 3
                triple = ""
                continue
            # Fine stringa normale.
            if not triple and ch == string_quote:
                state = "code"
                emit(ch if keep_strings else " ")
                i += 1
                continue
            # Una stringa normale non attraversa i newline.
            if not triple and ch == "\n":
                state = "code"
                emit("\n")
                i += 1
                continue
            emit(ch if keep_strings else ("\n" if ch == "\n" else " "))
            i += 1
            continue

    return "".join(out)


def strip_comments(source: str, language: Optional[str]) -> str:
    """Rimuove i commenti mantenendo le stringhe."""
    return _scrub(source, language, keep_strings=True)


def mask_code(source: str, language: Optional[str]) -> str:
    """Rimuove commenti e contenuto delle stringhe (analisi strutturale)."""
    return _scrub(source, language, keep_strings=False)


def count_code_lines(source: str) -> int:
    """Conta le righe non vuote (approssimazione delle righe di codice)."""
    return sum(1 for line in source.splitlines() if line.strip())
