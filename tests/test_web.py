import pytest

from greenindex.web.fetch import parse_github_target

flask = pytest.importorskip("flask")
from greenindex.web.app import create_app  # noqa: E402


# ----------------------------- fetch parser ------------------------------- #
def test_parse_github_full_url():
    assert parse_github_target("https://github.com/leofurio/GreenIndex") == ("leofurio", "GreenIndex")


def test_parse_github_with_git_suffix_and_subpath():
    assert parse_github_target("https://github.com/u/r.git") == ("u", "r")
    assert parse_github_target("github.com/u/r/tree/main") == ("u", "r")


def test_parse_github_shorthand():
    assert parse_github_target("leofurio/GreenIndex") == ("leofurio", "GreenIndex")


def test_parse_github_rejects_other_hosts():
    assert parse_github_target("https://gitlab.com/u/r") is None
    assert parse_github_target("https://evil.example.com/u/r") is None
    assert parse_github_target("not a repo") is None
    assert parse_github_target("") is None


def test_parse_github_rejects_ssrf_localhost():
    assert parse_github_target("http://127.0.0.1/u/r") is None
    assert parse_github_target("http://localhost:8000/a/b") is None


# ------------------------------- hosted app -------------------------------- #
@pytest.fixture
def hosted_client():
    return create_app({"HOSTED": True, "INLINE_CSS": True}).test_client()


@pytest.fixture
def local_client():
    return create_app({"HOSTED": False, "INLINE_CSS": False}).test_client()


def test_hosted_home_shows_github_and_snippet_forms(hosted_client):
    html = hosted_client.get("/").data
    assert b"/analyze-snippet" in html
    assert b"repository GitHub" in html
    # In modalità hosted il CSS è inlineato (niente link a /static).
    assert b"<style>" in html


def test_local_home_shows_local_form(local_client):
    html = local_client.get("/").data
    assert b"/analyze-snippet" not in html
    assert b"Percorso locale" in html


def test_hosted_rejects_non_github_target(hosted_client):
    r = hosted_client.post("/analyze", data={"target": "https://gitlab.com/u/r"})
    assert r.status_code == 400
    assert "GitHub".encode() in r.data


def test_snippet_analysis_detects_violation(hosted_client):
    code = "for i in a:\n    for j in b:\n        print(i, j)\n"
    r = hosted_client.post("/analyze-snippet", data={"code": code, "language": "python"})
    assert r.status_code == 200
    assert b"gauge-grade" in r.data       # ha renderizzato il report
    assert b"GC001" in r.data             # ciclo annidato rilevato


def test_snippet_empty_is_rejected(hosted_client):
    r = hosted_client.post("/analyze-snippet", data={"code": "  ", "language": "python"})
    assert r.status_code == 400


def test_healthz(hosted_client):
    j = hosted_client.get("/healthz").get_json()
    assert j["status"] == "ok"
    assert j["hosted"] is True


def test_rules_page_is_linked_from_home(hosted_client):
    html = hosted_client.get("/").data
    assert b'href="/rules"' in html
    assert b"Regole" in html


def test_rules_page_lists_rules_and_calculation(hosted_client):
    r = hosted_client.get("/rules")
    assert r.status_code == 200
    assert "Regole applicate da GreenIndex".encode() in r.data
    assert b"GC023" in r.data
    assert b"GC032" in r.data
    assert b"GC052" in r.data
    assert b"kWh/anno" in r.data
    assert "CO₂e".encode() in r.data


# ------------------------------ impact counter ----------------------------- #
def test_counter_hidden_when_no_repos(tmp_path):
    # Nota: in hosted il CSS è inlineato, quindi la *classe* .impact-counter
    # compare comunque; come marcatore della sezione usiamo il testo visibile.
    import os

    os.environ["GREENINDEX_STATS_FILE"] = str(tmp_path / "stats.json")
    os.environ.pop("KV_REST_API_URL", None)
    os.environ.pop("KV_REST_API_TOKEN", None)
    try:
        client = create_app({"HOSTED": True, "INLINE_CSS": True}).test_client()
        assert b"repo analizzati" not in client.get("/").data
    finally:
        os.environ.pop("GREENINDEX_STATS_FILE", None)


def test_snippet_does_not_count_as_repo(tmp_path):
    import os

    os.environ["GREENINDEX_STATS_FILE"] = str(tmp_path / "stats.json")
    os.environ.pop("KV_REST_API_URL", None)
    os.environ.pop("KV_REST_API_TOKEN", None)
    try:
        client = create_app({"HOSTED": True, "INLINE_CSS": True}).test_client()
        client.post("/analyze-snippet", data={"code": "print('x')\n", "language": "python"})
        assert b"repo analizzati" not in client.get("/").data
    finally:
        os.environ.pop("GREENINDEX_STATS_FILE", None)


def test_counter_shows_recorded_repos(tmp_path):
    import os

    os.environ["GREENINDEX_STATS_FILE"] = str(tmp_path / "stats.json")
    os.environ.pop("KV_REST_API_URL", None)
    os.environ.pop("KV_REST_API_TOKEN", None)
    try:
        client = create_app({"HOSTED": True, "INLINE_CSS": True}).test_client()
        # Registriamo direttamente nello store per non dipendere dalla rete.
        from greenindex.web.stats import create_stats_store

        create_stats_store({"HOSTED": True}).record(12.5)
        html = client.get("/").data
        assert b"repo analizzati" in html
        assert "kWh che abbiamo aiutato a ottimizzare".encode() in html
    finally:
        os.environ.pop("GREENINDEX_STATS_FILE", None)


def test_file_stats_store_persists_and_accumulates(tmp_path):
    from greenindex.web.stats import FileStatsStore

    store = FileStatsStore(str(tmp_path / "s.json"))
    store.record(2.0)
    store.record(3.5)
    snap = store.snapshot()
    assert snap.repos == 2
    assert snap.kwh == pytest.approx(5.5)
    # Un nuovo store sullo stesso file rilegge i totali persistiti.
    assert FileStatsStore(str(tmp_path / "s.json")).snapshot().repos == 2
