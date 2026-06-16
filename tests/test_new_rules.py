"""Test per le regole aggiunte (GC004-GC013, GC033, GC042, GC064, GC071-GC072, GC082-GC084)."""

import os

from greenindex.analyzer import Analyzer


def _snippet_ids(name, src, lang=None):
    result = Analyzer().analyze_source(name, src, language=lang)
    assert not result.errors, result.errors
    return {v.rule_id for v in result.violations}


def _repo_ids(tmp_path, filename, content):
    (tmp_path / filename).write_text(content, encoding="utf-8")
    result = Analyzer().analyze(str(tmp_path))
    return {v.rule_id for v in result.violations}


# ------------------------------- compute ---------------------------------- #
def test_gc004_regex_in_loop():
    assert "GC004" in _snippet_ids("a.py", "import re\nfor x in y:\n    re.search('a', x)\n")


def test_gc005_sleep_in_async():
    assert "GC005" in _snippet_ids("a.py", "import time\nasync def f():\n    time.sleep(1)\n")


def test_gc005_not_flagged_in_sync_function():
    assert "GC005" not in _snippet_ids("a.py", "import time\ndef f():\n    time.sleep(1)\n")


def test_gc006_iterrows():
    assert "GC006" in _snippet_ids("a.py", "for i, row in df.iterrows():\n    pass\n")


def test_gc007_sort_in_loop():
    assert "GC007" in _snippet_ids("a.py", "for x in y:\n    z = sorted(x)\n")


def test_gc008_membership_literal_in_loop():
    assert "GC008" in _snippet_ids("a.py", "for x in y:\n    if x in [1, 2, 3]:\n        pass\n")


def test_gc008_not_flagged_for_set():
    assert "GC008" not in _snippet_ids("a.py", "for x in y:\n    if x in {1, 2, 3}:\n        pass\n")


def test_gc009_recursion_without_memo():
    assert "GC009" in _snippet_ids("a.py", "def fib(n):\n    return fib(n - 1) + fib(n - 2)\n")


def test_gc009_not_flagged_with_cache():
    code = "import functools\n@functools.lru_cache\ndef fib(n):\n    return fib(n-1) + fib(n-2)\n"
    assert "GC009" not in _snippet_ids("a.py", code)


def test_gc009_not_flagged_single_self_call():
    assert "GC009" not in _snippet_ids("a.py", "def f(n):\n    return f(n - 1)\n")


# ------------------------------- memory ----------------------------------- #
def test_gc012_list_materialization():
    assert "GC012" in _snippet_ids("a.py", "total = sum([i for i in data])\n")


def test_gc012_not_flagged_for_generator():
    assert "GC012" not in _snippet_ids("a.py", "total = sum(i for i in data)\n")


def test_gc013_deepcopy_in_loop():
    assert "GC013" in _snippet_ids("a.py", "import copy\nfor x in y:\n    copy.deepcopy(x)\n")


# -------------------------------- data ------------------------------------ #
def test_gc033_leading_wildcard_like():
    assert "GC033" in _snippet_ids("q.sql", "SELECT a FROM t WHERE name LIKE '%foo%';\n")


def test_gc033_not_flagged_for_trailing_wildcard():
    assert "GC033" not in _snippet_ids("q.sql", "SELECT a FROM t WHERE name LIKE 'foo%';\n")


# ---------------------------- observability ------------------------------- #
def test_gc042_eager_log_fstring():
    assert "GC042" in _snippet_ids("a.py", "import logging\nlogging.debug(f'x={x}')\n")


def test_gc042_not_flagged_for_lazy_logging():
    assert "GC042" not in _snippet_ids("a.py", "import logging\nlogging.debug('x=%s', x)\n")


# -------------------------------- energy ---------------------------------- #
def test_gc064_autoplay_media():
    assert "GC064" in _snippet_ids("p.html", "<video autoplay src='x.mp4'></video>\n")


# -------------------------------- assets ---------------------------------- #
def test_gc071_img_without_lazy():
    assert "GC071" in _snippet_ids("p.html", "<img src='a.png'>\n")


def test_gc071_not_flagged_with_lazy():
    assert "GC071" not in _snippet_ids("p.html", "<img src='a.png' loading='lazy'>\n")


def test_gc072_large_unminified_bundle(tmp_path):
    (tmp_path / "vendor.js").write_text("x = 1;\n" * 30000, encoding="utf-8")
    result = Analyzer().analyze(str(tmp_path))
    assert "GC072" in {v.rule_id for v in result.violations}


def test_gc072_not_flagged_for_minified(tmp_path):
    (tmp_path / "vendor.min.js").write_text("var x=1;" * 30000, encoding="utf-8")
    result = Analyzer().analyze(str(tmp_path))
    assert "GC072" not in {v.rule_id for v in result.violations}


# ----------------------------- infrastructure ----------------------------- #
def test_gc082_pip_without_no_cache(tmp_path):
    assert "GC082" in _repo_ids(tmp_path, "Dockerfile", "FROM python:3.12-slim\nRUN pip install flask\n")


def test_gc083_non_slim_base(tmp_path):
    assert "GC083" in _repo_ids(tmp_path, "Dockerfile", "FROM python:3.12\nRUN echo hi\n")


def test_gc083_not_flagged_for_slim(tmp_path):
    assert "GC083" not in _repo_ids(tmp_path, "Dockerfile", "FROM python:3.12-slim\nRUN echo hi\n")


def test_gc084_add_instead_of_copy(tmp_path):
    assert "GC084" in _repo_ids(tmp_path, "Dockerfile", "FROM alpine\nADD app.py /app/app.py\n")
