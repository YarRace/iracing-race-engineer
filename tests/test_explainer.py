import json
from ire.explainer.explainer import build_prompt, parse_response

def test_prompt_contains_symptoms_and_setup():
    sym = json.load(open("tests/fixtures/sample_symptoms.json"))
    p = build_prompt(sym, setup_fields={"Front tire pressure": 138}, car="Cadillac GTP", track="Watkins Glen")
    assert "Cadillac GTP" in p and "Watkins Glen" in p and "balance" in p

def test_parse_extracts_driving_setup_delta():
    fake = json.dumps({
        "driving": ["Тормози позже в Т1"],
        "setup_changes": [{"field": "Front tire pressure", "from": 138, "to": 140, "why": "перегрев центра"}],
        "delta": {"Front tire pressure": 140},
    })
    r = parse_response(fake)
    assert r["driving"] and r["setup_changes"][0]["field"] == "Front tire pressure"
    assert r["delta"]["Front tire pressure"] == 140
