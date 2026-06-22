"""Rendering dei risultati: terminale, JSON e HTML.

L'HTML è generato con gli stessi template Jinja usati dalla dashboard web,
così CLI e web producono lo stesso report. L'export da CLI inlinea il CSS per
ottenere un file autonomo apribile con un doppio clic.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Dict, List, Optional

from . import __version__
from .analyzer import AnalysisResult
from .rules import CATEGORIES, Rule, Violation, rules_by_id
from .scoring import GRADE_BANDS, GreenIndexResult

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "web", "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "web", "static")

# Severità -> colore ANSI per il terminale.
_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}


# --------------------------------------------------------------------------- #
# Costruzione del contesto condiviso (CLI HTML + web).
# --------------------------------------------------------------------------- #
def build_context(index: GreenIndexResult, result: AnalysisResult,
                  root_label: str, rules: Optional[List[Rule]] = None) -> Dict:
    rule_map = rules_by_id(rules if rules is not None else result.rules)

    severity_rank = {v.rule_id: rule_map[v.rule_id].severity
                     for v in result.violations if v.rule_id in rule_map}
    sorted_violations = sorted(
        [v for v in result.violations if v.rule_id in rule_map],
        key=lambda v: (-severity_rank.get(v.rule_id, 0), v.path, v.line),
    )

    return {
        "version": __version__,
        "root_label": root_label,
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "index": index,
        "result": result,
        "rules_by_id": rule_map,
        "categories_meta": CATEGORIES,
        "grade_bands": GRADE_BANDS,
        "language_breakdown": result.language_breakdown,
        "violations": sorted_violations,
        "violation_count": len(sorted_violations),
    }


# --------------------------------------------------------------------------- #
# Terminale.
# --------------------------------------------------------------------------- #
def render_terminal(index: GreenIndexResult, result: AnalysisResult,
                    root_label: str, color: bool = True) -> str:
    def c(text: str, *styles: str) -> str:
        if not color:
            return text
        return "".join(_ANSI[s] for s in styles) + text + _ANSI["reset"]

    grade_color = {
        "A": "green", "B": "green", "C": "yellow",
        "D": "yellow", "E": "red", "F": "red", "G": "red",
    }.get(index.grade, "cyan")

    lines: List[str] = []
    lines.append("")
    lines.append(c("  GreenIndex", "bold", "cyan") + c(f"  v{__version__}", "grey"))
    lines.append(c(f"  Repository: {root_label}", "grey"))
    lines.append("")

    # Punteggio + barra.
    bar_len = 30
    filled = int(round(index.score / 100 * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)
    lines.append(
        f"  {c('GreenIndex', 'bold')}: "
        f"{c(f'{index.score:5.1f}/100', 'bold', grade_color)}  "
        f"{c(bar, grade_color)}  "
        f"{c('classe ' + index.grade, 'bold', grade_color)} ({index.grade_label})"
    )
    lines.append(
        c(f"  {result.total_code_lines} righe di codice • "
          f"{result.code_files} file di codice • "
          f"{index.total_violations} violazioni • "
          f"densità {index.density:.1f} pen./KLOC", "grey")
    )
    lines.append("")

    if not result.violations:
        lines.append(c("  ✔ Nessuna violazione rilevata. Ottimo lavoro!", "green", "bold"))
        lines.append("")
        return "\n".join(lines)

    # Categorie.
    lines.append(c("  Impatto per categoria", "bold"))
    for cs in index.categories:
        cat_bar_len = 24
        cat_filled = int(round(cs.percent_of_penalty / 100 * cat_bar_len)) if cs.percent_of_penalty else 0
        cat_bar = "▰" * cat_filled + "▱" * (cat_bar_len - cat_filled)
        icon = CATEGORIES.get(cs.category, {}).get("icon", "•")
        lines.append(
            f"    {icon} {cs.label:<22} {c(cat_bar, 'cyan')} "
            f"{cs.percent_of_penalty:5.1f}%  "
            f"{c(f'({cs.count} viol.)', 'grey')}"
        )
    lines.append("")

    # Regole più impattanti.
    lines.append(c("  Regole più impattanti", "bold"))
    for rs in index.rules[:8]:
        sev_color = "red" if rs.severity >= 4 else ("yellow" if rs.severity >= 3 else "grey")
        lines.append(
            f"    {c(rs.rule_id, 'bold')}  {rs.name[:46]:<46} "
            f"{c(f'×{rs.count}', sev_color)}  "
            f"{c(f'(-{rs.penalty})', 'grey')}"
        )
    lines.append("")

    # Prime violazioni.
    ctx_violations = sorted(
        result.violations,
        key=lambda v: (-rules_by_id(result.rules).get(v.rule_id, _DUMMY).severity, v.path, v.line),
    )
    lines.append(c(f"  Dettaglio violazioni (prime {min(15, len(ctx_violations))} di {len(ctx_violations)})", "bold"))
    for v in ctx_violations[:15]:
        loc = f"{v.path}:{v.line}" if v.line else v.path
        lines.append(f"    {c(v.rule_id, 'cyan')} {c(loc, 'grey')}")
        if v.snippet:
            lines.append(f"        {c(v.snippet[:90], 'dim')}")
    if len(ctx_violations) > 15:
        lines.append(c(f"    … e altre {len(ctx_violations) - 15} violazioni", "grey"))
    lines.append("")

    return "\n".join(lines)


class _Dummy:
    severity = 0


_DUMMY = _Dummy()


# --------------------------------------------------------------------------- #
# JSON.
# --------------------------------------------------------------------------- #
def to_json_dict(index: GreenIndexResult, result: AnalysisResult,
                 root_label: str) -> Dict:
    rule_map = rules_by_id(result.rules)
    return {
        "tool": "greenindex",
        "version": __version__,
        "repository": root_label,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "green_index": index.as_dict(),
        "stats": {
            "total_files": result.total_files,
            "code_files": result.code_files,
            "total_code_lines": result.total_code_lines,
            "language_breakdown": result.language_breakdown,
        },
        "violations": [
            {
                "rule_id": v.rule_id,
                "rule_name": rule_map[v.rule_id].name if v.rule_id in rule_map else v.rule_id,
                "category": rule_map[v.rule_id].category if v.rule_id in rule_map else None,
                "severity": rule_map[v.rule_id].severity if v.rule_id in rule_map else None,
                "path": v.path,
                "line": v.line,
                "column": v.column,
                "message": v.message,
                "snippet": v.snippet,
            }
            for v in result.violations
        ],
        "errors": result.errors,
    }


# --------------------------------------------------------------------------- #
# HTML.
# --------------------------------------------------------------------------- #
def _format_it_number(value, decimals: int = 0) -> str:
    """Formatta un numero in stile italiano (1.234,5).

    Usa il punto come separatore delle migliaia e la virgola per i decimali.
    Robusto a valori non numerici (restituisce stringa vuota).
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    formatted = f"{number:,.{decimals}f}"  # es. "1,234.5"
    # Scambia i separatori anglosassoni con quelli italiani.
    return formatted.replace(",", " ").replace(".", ",").replace(" ", ".")


def register_filters(env) -> None:
    """Registra i filtri Jinja usati dai template (CLI e web)."""
    from .rules import SEVERITY_LABELS

    env.filters["sevlabel"] = lambda s: SEVERITY_LABELS.get(s, str(s))
    env.filters["itnum"] = _format_it_number


def _jinja_env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    register_filters(env)
    return env


def _read_css() -> str:
    path = os.path.join(STATIC_DIR, "style.css")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def render_html(index: GreenIndexResult, result: AnalysisResult,
                root_label: str) -> str:
    env = _jinja_env()
    template = env.get_template("report.html")
    context = build_context(index, result, root_label)
    context["inline_css"] = _read_css()
    context["standalone"] = True
    return template.render(**context)
