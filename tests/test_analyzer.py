import os

from greenindex.analyzer import Analyzer, detect_nested_loops_clike
from greenindex.textutils import mask_code


def _rule_ids(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    result = Analyzer().analyze(str(tmp_path))
    return {v.rule_id for v in result.violations}, result


def test_python_nested_loops(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.py", "for i in x:\n    for j in y:\n        pass\n")
    assert "GC001" in ids


def test_python_request_in_loop_and_timeout(tmp_path):
    code = "import requests\nfor u in users:\n    requests.get('http://x/' + u)\n"
    ids, _ = _rule_ids(tmp_path, "a.py", code)
    assert "GC020" in ids  # rete dentro ciclo
    assert "GC022" in ids  # senza timeout


def test_open_without_with(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.py", "f = open('x')\ndata = f.read()\n")
    assert "GC011" in ids
    assert "GC010" in ids


def test_with_open_is_clean(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.py", "with open('x') as f:\n    data = f.read()\n")
    assert "GC011" not in ids


def test_string_concat_in_loop(tmp_path):
    code = "s = ''\nfor i in x:\n    s += str(i) + '!'\n"
    ids, _ = _rule_ids(tmp_path, "a.py", code)
    assert "GC002" in ids


def test_busy_wait(tmp_path):
    code = "import time\nwhile True:\n    time.sleep(1)\n"
    ids, _ = _rule_ids(tmp_path, "a.py", code)
    assert "GC003" in ids


def test_print_debug(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.py", "print('hi')\n")
    assert "GC040" in ids


def test_select_star_sql(tmp_path):
    ids, _ = _rule_ids(tmp_path, "q.sql", "SELECT * FROM orders WHERE x = 1;\n")
    assert "GC030" in ids


def test_js_nested_loops(tmp_path):
    code = "for (let i=0;i<n;i++) {\n  for (let j=0;j<m;j++) {\n    f();\n  }\n}\n"
    ids, _ = _rule_ids(tmp_path, "a.js", code)
    assert "GC001" in ids


def test_set_interval_high_frequency(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.js", "setInterval(() => f(), 16);\n")
    assert "GC063" in ids


def test_css_infinite_animation(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.css", ".x { animation: spin 1s linear infinite; }\n")
    assert "GC061" in ids


def test_dockerfile_latest_and_no_multistage(tmp_path):
    ids, _ = _rule_ids(tmp_path, "Dockerfile", "FROM python:latest\nRUN pip install x\n")
    assert "GC080" in ids
    assert "GC081" in ids


def test_heavy_dependency(tmp_path):
    ids, _ = _rule_ids(tmp_path, "requirements.txt", "tensorflow>=2.0\nflask\n")
    assert "GC051" in ids


def test_markdown_not_scanned(tmp_path):
    # "select * from" nella documentazione non deve generare violazioni.
    ids, _ = _rule_ids(tmp_path, "README.md", "Esempio: SELECT * FROM t;\n")
    assert "GC030" not in ids


def test_cryptomining_detected_in_usage(tmp_path):
    code = "var miner = new CoinHive.Anonymous('SITE_KEY');\nminer.start();\n"
    ids, _ = _rule_ids(tmp_path, "a.js", code)
    assert "GC062" in ids


def test_cryptomining_not_flagged_for_keyword_list(tmp_path):
    # Un semplice elenco di parole chiave non deve generare un falso positivo.
    code = "blocklist = ['coinhive', 'cryptonight', 'deepminer']\n"
    ids, _ = _rule_ids(tmp_path, "a.py", code)
    assert "GC062" not in ids


def test_nested_loop_detector_unit():
    code = "for(;;){ for(;;){ } }"
    assert detect_nested_loops_clike(mask_code(code, "c"))


def test_no_false_nested_loop_for_arrow():
    code = "setInterval(() => { run(); }, 100);"
    assert not detect_nested_loops_clike(mask_code(code, "javascript"))


def test_js_fetch_without_abort_or_timeout(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.js", "fetch('/api/data');\n")
    assert "GC023" in ids


def test_js_fetch_with_abort_signal_is_clean(tmp_path):
    ids, _ = _rule_ids(tmp_path, "a.js", "fetch('/api/data', { signal: controller.signal });\n")
    assert "GC023" not in ids


def test_update_delete_without_where(tmp_path):
    ids, _ = _rule_ids(tmp_path, "q.sql", "UPDATE users SET active = 0;\nDELETE FROM logs;\n")
    assert "GC032" in ids


def test_unpinned_dependency(tmp_path):
    ids, _ = _rule_ids(tmp_path, "requirements.txt", "flask\nrequests>=2\n")
    assert "GC052" in ids


def test_package_json_unpinned_dependency_only_in_dependency_sections(tmp_path):
    pkg = '''{
      "name": "x",
      "version": "1.0.0",
      "dependencies": {
        "lodash": "*",
        "flask": "latest"
      }
    }
'''
    ids, result = _rule_ids(tmp_path, "package.json", pkg)
    assert "GC052" in ids
    assert sum(1 for v in result.violations if v.rule_id == "GC052") == 2
