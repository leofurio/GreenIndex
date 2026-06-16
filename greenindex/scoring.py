"""Calcolo del KPI GreenIndex e della classe di efficienza energetica.

Il punteggio parte da 100 e viene ridotto in funzione della *densità* di
penalità (somma dei pesi di gravità per ogni 1000 righe di codice), così che
repository grandi e piccoli siano confrontabili.

    penalità   = Σ gravità(violazione)
    densità    = penalità / max(KLOC, KLOC_min)
    GreenIndex = clamp(100 - K · densità, 0, 100)

Al punteggio è associata una classe A-G in stile etichetta energetica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .analyzer import AnalysisResult
from .rules import CATEGORIES, Rule, Violation, rules_by_id

# Costante di scala: con K=1.0 una densità di 50 penalità/KLOC -> punteggio 50.
DEFAULT_K = 1.0
# KLOC minimo per evitare che micro-repository esplodano in densità.
MIN_KLOC = 0.1

# Bande di voto in stile etichetta energetica (soglia minima inclusiva).
GRADE_BANDS = [
    ("A", 90.0, "#2e7d32", "Eccellente"),
    ("B", 80.0, "#558b2f", "Ottimo"),
    ("C", 70.0, "#9e9d24", "Buono"),
    ("D", 60.0, "#f9a825", "Sufficiente"),
    ("E", 45.0, "#ef6c00", "Migliorabile"),
    ("F", 25.0, "#d84315", "Scarso"),
    ("G", 0.0, "#b71c1c", "Critico"),
]

# Coefficienti puramente ILLUSTRATIVI per dare un ordine di grandezza
# all'impatto. NON sono una misura scientifica di emissioni: GreenIndex è
# un'analisi statica e non esegue il codice. Vedi la pagina /rules ("Da dove
# arriva la stima di CO2?") per la spiegazione mostrata all'utente.
#
# kWh per punto: convenzione didattica (nessuna base empirica), serve solo a
# tradurre i punti astratti di penalità in un ordine di grandezza tangibile.
ILLUSTRATIVE_KWH_PER_POINT = 0.05  # kWh/anno indicativi per punto di penalità
# kg CO2e per kWh: intensità di carbonio della rete elettrica. Il valore reale
# varia molto (da ~0.05 su reti idro/nucleare a >0.7 su reti a carbone; media
# globale ~0.45-0.48, europea ~0.25-0.30 secondo IEA/Ember/Our World in Data).
# 0.30 è un valore intermedio indicativo.
ILLUSTRATIVE_KG_CO2_PER_KWH = 0.30


@dataclass
class CategoryScore:
    category: str
    label: str
    color: str
    count: int
    penalty: int

    @property
    def percent_of_penalty(self) -> float:
        return self._percent

    _percent: float = 0.0


@dataclass
class RuleScore:
    rule_id: str
    name: str
    category: str
    severity: int
    count: int
    penalty: int


@dataclass
class GreenIndexResult:
    """KPI GreenIndex e relativi dettagli."""

    score: float
    grade: str
    grade_color: str
    grade_label: str
    penalty: int
    density: float
    code_lines: int
    total_violations: int
    categories: List[CategoryScore] = field(default_factory=list)
    rules: List[RuleScore] = field(default_factory=list)
    illustrative_kwh: float = 0.0
    illustrative_kg_co2: float = 0.0

    def as_dict(self) -> Dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "grade_color": self.grade_color,
            "grade_label": self.grade_label,
            "penalty": self.penalty,
            "density": round(self.density, 2),
            "code_lines": self.code_lines,
            "total_violations": self.total_violations,
            "illustrative_kwh": round(self.illustrative_kwh, 2),
            "illustrative_kg_co2": round(self.illustrative_kg_co2, 2),
            "categories": [
                {
                    "category": c.category,
                    "label": c.label,
                    "color": c.color,
                    "count": c.count,
                    "penalty": c.penalty,
                    "percent_of_penalty": round(c.percent_of_penalty, 1),
                }
                for c in self.categories
            ],
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "category": r.category,
                    "severity": r.severity,
                    "count": r.count,
                    "penalty": r.penalty,
                }
                for r in self.rules
            ],
        }


def grade_for_score(score: float) -> tuple:
    """Restituisce (lettera, colore, etichetta) per un punteggio."""
    for letter, threshold, color, label in GRADE_BANDS:
        if score >= threshold:
            return letter, color, label
    last = GRADE_BANDS[-1]
    return last[0], last[2], last[3]


def compute_green_index(result: AnalysisResult,
                        rules: Optional[List[Rule]] = None,
                        k: float = DEFAULT_K) -> GreenIndexResult:
    """Calcola il GreenIndex a partire da un :class:`AnalysisResult`."""
    rule_map = rules_by_id(rules if rules is not None else result.rules)

    penalty = 0
    cat_count: Dict[str, int] = {}
    cat_penalty: Dict[str, int] = {}
    rule_count: Dict[str, int] = {}
    rule_penalty: Dict[str, int] = {}

    for v in result.violations:
        rule = rule_map.get(v.rule_id)
        if rule is None:
            continue
        penalty += rule.severity
        cat_count[rule.category] = cat_count.get(rule.category, 0) + 1
        cat_penalty[rule.category] = cat_penalty.get(rule.category, 0) + rule.severity
        rule_count[v.rule_id] = rule_count.get(v.rule_id, 0) + 1
        rule_penalty[v.rule_id] = rule_penalty.get(v.rule_id, 0) + rule.severity

    code_lines = max(result.total_code_lines, 1)
    kloc = max(code_lines / 1000.0, MIN_KLOC)
    density = penalty / kloc
    score = max(0.0, min(100.0, 100.0 - k * density))
    score = round(score, 1)

    letter, color, label = grade_for_score(score)

    # Dettaglio per categoria.
    categories: List[CategoryScore] = []
    for cat, meta in CATEGORIES.items():
        if cat not in cat_count:
            continue
        cs = CategoryScore(
            category=cat,
            label=meta["label"],
            color=meta["color"],
            count=cat_count[cat],
            penalty=cat_penalty[cat],
        )
        cs._percent = (cat_penalty[cat] / penalty * 100.0) if penalty else 0.0
        categories.append(cs)
    categories.sort(key=lambda c: c.penalty, reverse=True)

    # Dettaglio per regola.
    rule_scores: List[RuleScore] = []
    for rid, cnt in rule_count.items():
        rule = rule_map[rid]
        rule_scores.append(
            RuleScore(
                rule_id=rid,
                name=rule.name,
                category=rule.category,
                severity=rule.severity,
                count=cnt,
                penalty=rule_penalty[rid],
            )
        )
    rule_scores.sort(key=lambda r: (r.penalty, r.count), reverse=True)

    illustrative_kwh = penalty * ILLUSTRATIVE_KWH_PER_POINT
    illustrative_kg_co2 = illustrative_kwh * ILLUSTRATIVE_KG_CO2_PER_KWH

    return GreenIndexResult(
        score=score,
        grade=letter,
        grade_color=color,
        grade_label=label,
        penalty=penalty,
        density=density,
        code_lines=result.total_code_lines,
        total_violations=len(result.violations),
        categories=categories,
        rules=rule_scores,
        illustrative_kwh=illustrative_kwh,
        illustrative_kg_co2=illustrative_kg_co2,
    )
