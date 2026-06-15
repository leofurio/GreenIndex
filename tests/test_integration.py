import json
import os

from greenindex.analyzer import Analyzer
from greenindex.report import render_html, render_terminal, to_json_dict
from greenindex.scoring import compute_green_index

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "examples", "sample_project")


def _analyze_sample():
    result = Analyzer().analyze(SAMPLE)
    index = compute_green_index(result)
    return result, index


def test_sample_project_has_expected_violations():
    result, index = _analyze_sample()
    found = {v.rule_id for v in result.violations}
    # Un sottoinsieme rappresentativo delle regole esercitate dal sample.
    for rid in ["GC001", "GC002", "GC003", "GC010", "GC011", "GC020",
                "GC021", "GC030", "GC040", "GC051", "GC060", "GC080"]:
        assert rid in found, f"regola attesa mancante: {rid}"


def test_sample_score_is_low_grade():
    _, index = _analyze_sample()
    assert 0 <= index.score < 100
    assert index.grade in {"D", "E", "F", "G", "C"}
    assert index.total_violations > 10


def test_json_report_is_serializable():
    result, index = _analyze_sample()
    payload = to_json_dict(index, result, "sample")
    text = json.dumps(payload)  # non deve sollevare eccezioni
    data = json.loads(text)
    assert data["tool"] == "greenindex"
    assert data["green_index"]["grade"] in list("ABCDEFG")
    assert len(data["violations"]) == index.total_violations


def test_html_report_renders():
    result, index = _analyze_sample()
    html = render_html(index, result, "sample")
    assert "<html" in html.lower()
    assert "GreenIndex" in html
    assert index.grade in html


def test_terminal_report_renders():
    result, index = _analyze_sample()
    out = render_terminal(index, result, "sample", color=False)
    assert "GreenIndex" in out
    assert "classe" in out
