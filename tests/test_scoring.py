from greenindex.analyzer import AnalysisResult, FileStat
from greenindex.rules import DEFAULT_RULES, Violation
from greenindex.scoring import compute_green_index, grade_for_score


def _result_with(violations, code_lines):
    res = AnalysisResult(root=".", rules=list(DEFAULT_RULES))
    res.files.append(FileStat(path="a.py", language="python", code_lines=code_lines, bytes=0))
    res.violations.extend(violations)
    return res


def test_perfect_score_when_no_violations():
    res = _result_with([], 500)
    idx = compute_green_index(res)
    assert idx.score == 100.0
    assert idx.grade == "A"
    assert idx.total_violations == 0


def test_score_decreases_with_violations():
    # GC001 ha gravità 3; 10 occorrenze => penalità 30 su 1 KLOC => densità 30.
    violations = [Violation(rule_id="GC001", path="a.py", line=i) for i in range(10)]
    res = _result_with(violations, 1000)
    idx = compute_green_index(res)
    assert idx.penalty == 30
    assert abs(idx.density - 30.0) < 0.01
    assert abs(idx.score - 70.0) < 0.01
    assert idx.grade == "C"


def test_score_is_clamped_to_zero():
    violations = [Violation(rule_id="GC062", path="a.py", line=i) for i in range(100)]
    res = _result_with(violations, 50)
    idx = compute_green_index(res)
    assert idx.score == 0.0
    assert idx.grade == "G"


def test_grade_bands():
    assert grade_for_score(95)[0] == "A"
    assert grade_for_score(85)[0] == "B"
    assert grade_for_score(75)[0] == "C"
    assert grade_for_score(65)[0] == "D"
    assert grade_for_score(50)[0] == "E"
    assert grade_for_score(30)[0] == "F"
    assert grade_for_score(10)[0] == "G"


def test_category_breakdown_percent_sums_to_100():
    violations = [
        Violation(rule_id="GC001", path="a.py", line=1),  # compute, sev 3
        Violation(rule_id="GC040", path="a.py", line=2),  # observability, sev 1
    ]
    res = _result_with(violations, 1000)
    idx = compute_green_index(res)
    total = sum(c.percent_of_penalty for c in idx.categories)
    assert abs(total - 100.0) < 0.1
