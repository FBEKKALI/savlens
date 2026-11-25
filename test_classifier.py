import pytest

import classifier as c


def test_safety_triggers_escalation():
    t = c.classify_rules("Ma bouilloire dégage une odeur de brûlé et de la fumée.")
    assert t.category == "produit_defectueux"
    assert t.severity == 3 and t.needs_escalation and t.is_non_conform
    assert t.suggested_action.startswith("ESCALADE")


def test_description_mismatch():
    t = c.classify_rules("Le canapé ne correspond pas à la description du site.")
    assert t.category == "non_conforme_description" and t.severity == 1


def test_accents_and_case_are_ignored():
    assert c.classify_rules("Colis ABÎMÉ à la réception").category == "produit_endommage"


def test_delivery_delay_is_not_a_non_conformity():
    t = c.classify_rules("La commande a dix jours de retard.")
    assert t.category == "retard_livraison" and not t.is_non_conform and t.severity == 0


def test_positive_review():
    t = c.classify_rules("Très satisfait, je recommande.")
    assert t.category == "avis_positif" and not t.needs_escalation


def test_build_is_consistent_for_invalid_llm_output():
    t = c._build("categorie_inconnue", 2, "x", "llm")
    assert t.category == "demande_info" and t.severity == 0 and not t.is_non_conform


def test_build_forces_non_conformity_when_safety_risk():
    t = c._build("avis_positif", 3, "x", "llm")
    assert t.category == "produit_defectueux" and t.needs_escalation


def test_llm_failure_falls_back_to_rules(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("API indisponible")

    monkeypatch.setattr(c, "classify_llm", boom)
    t = c.classify("Mon aspirateur est en panne.", backend="llm")
    assert t.backend == "rules(repli)" and t.category == "produit_defectueux"


def test_classify_many_keeps_order():
    items = [("Colis cassé", None), ("Très satisfait", None)]
    res = c.classify_many(items, backend="rules")
    assert [r.category for r in res] == ["produit_endommage", "avis_positif"]


def test_api_triage_validation():
    pytest.importorskip("flask")
    import app

    client = app.app.test_client()
    assert client.post("/api/triage", json={}).status_code == 400
    assert client.post("/api/triage", json={"text": "x", "backend": "nope"}).status_code == 400
    ok = client.post("/api/triage", json={"text": "Mon casque ne fonctionne plus."})
    assert ok.status_code == 200 and ok.get_json()["category"] == "produit_defectueux"
