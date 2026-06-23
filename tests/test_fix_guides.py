"""Test per le guide "come risolverlo" (FixGuide) associate alle regole."""

import pytest

from greenindex.rules import DEFAULT_RULES, FIX_GUIDES


def test_every_rule_has_a_fix_guide():
    """Ogni regola deve avere una guida di rimedio dettagliata."""
    missing = [r.id for r in DEFAULT_RULES if r.fix_guide is None]
    assert not missing, f"Regole senza FixGuide: {missing}"


def test_fix_guides_have_steps_and_example():
    for rule in DEFAULT_RULES:
        guide = rule.fix_guide
        assert guide.steps, f"{rule.id}: nessun passo operativo"
        assert guide.has_example, f"{rule.id}: nessun esempio prima/dopo"
        assert guide.bad and guide.good, f"{rule.id}: esempio incompleto"


def test_no_orphan_fix_guides():
    """Nessuna guida deve riferirsi a una regola inesistente."""
    rule_ids = {r.id for r in DEFAULT_RULES}
    orphans = set(FIX_GUIDES) - rule_ids
    assert not orphans, f"FixGuide orfane: {orphans}"


def test_rule_fix_guide_lookup_returns_none_for_unknown():
    from greenindex.rules import Rule

    bogus = Rule(id="ZZ999", name="x", category="compute", severity=1,
                 description="x", remediation="x")
    assert bogus.fix_guide is None


# ------------------------------- rendering -------------------------------- #
flask = pytest.importorskip("flask")
from greenindex.web.app import create_app  # noqa: E402


@pytest.fixture
def hosted_client():
    return create_app({"HOSTED": True, "INLINE_CSS": True}).test_client()


def test_report_shows_how_to_fix_detail(hosted_client):
    code = "for i in a:\n    for j in b:\n        print(i, j)\n"
    r = hosted_client.post("/analyze-snippet",
                           data={"code": code, "language": "python"})
    assert r.status_code == 200
    assert "Come risolverlo".encode() in r.data
    assert b"fix-example" in r.data
    assert "Da evitare".encode() in r.data
    assert b"Consigliato" in r.data


def test_rules_page_shows_how_to_fix_detail(hosted_client):
    r = hosted_client.get("/rules")
    assert r.status_code == 200
    assert "Come risolverlo".encode() in r.data
    assert b"fix-example" in r.data
