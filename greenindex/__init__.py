"""GreenIndex — misura quanto è "green" il tuo codice.

GreenIndex analizza un repository alla ricerca di violazioni di regole di
consumo tecnologico (anti-pattern che sprecano CPU, memoria, rete, energia)
e calcola un KPI sintetico (0-100) con una classe di efficienza A-G in stile
etichetta energetica.

Moduli principali:
    rules     -> definizione delle regole di consumo tecnologico
    analyzer  -> scansione del repository e rilevamento delle violazioni
    scoring   -> calcolo del KPI GreenIndex e della classe energetica
    report    -> rendering dei risultati (terminale, JSON, HTML)
    cli       -> interfaccia a riga di comando
    web.app   -> dashboard web (Flask)
"""

from __future__ import annotations

__version__ = "1.0.0"

from .rules import Rule, Violation, DEFAULT_RULES, CATEGORIES  # noqa: E402
from .analyzer import Analyzer, AnalysisResult  # noqa: E402
from .scoring import GreenIndexResult, compute_green_index  # noqa: E402

__all__ = [
    "__version__",
    "Rule",
    "Violation",
    "DEFAULT_RULES",
    "CATEGORIES",
    "Analyzer",
    "AnalysisResult",
    "GreenIndexResult",
    "compute_green_index",
]
