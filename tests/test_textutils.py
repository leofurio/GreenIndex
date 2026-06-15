from greenindex.textutils import (
    count_code_lines,
    detect_language,
    mask_code,
    strip_comments,
)


def test_detect_language():
    assert detect_language("a/b/main.py") == "python"
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("api.Dockerfile") == "dockerfile"
    assert detect_language("app.tsx") == "typescript"
    assert detect_language("styles.scss") == "css"
    assert detect_language("notes") is None


def test_strip_comments_keeps_strings():
    src = 'x = "select * from t"  # commento\n'
    cleaned = strip_comments(src, "python")
    assert "select * from t" in cleaned  # la stringa resta
    assert "commento" not in cleaned     # il commento sparisce


def test_mask_code_removes_strings_and_comments():
    src = 'x = "for while"  # for\n'
    masked = mask_code(src, "python")
    assert "for while" not in masked
    assert "for" not in masked


def test_line_numbers_preserved():
    src = "a\n# c1\n'''\nblock\n'''\nb\n"
    cleaned = strip_comments(src, "python")
    assert len(cleaned.splitlines()) == len(src.splitlines())


def test_clike_comments():
    src = "int x; // for\n/* while\nloop */ int y;\n"
    masked = mask_code(src, "c")
    assert "for" not in masked
    assert "while" not in masked
    assert "int x;" in masked


def test_count_code_lines():
    assert count_code_lines("a\n\n  \nb\n") == 2
