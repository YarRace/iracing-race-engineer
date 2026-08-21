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


def test_no_fake_car_and_track_in_prompt():
    """Раньше в explain() стояли значения по умолчанию «Cadillac GTP» и
    «Watkins Glen». Для Porsche на Monza модель получала прямую ложь про
    машину и трассу — и советовала сетап не от той машины."""
    p = build_prompt({}, setup_fields={}, car=None, track=None)
    assert "Cadillac" not in p and "Watkins" not in p
    # честнее сказать «неизвестно», чем назвать чужую машину
    assert "unknown" in p.lower()


def test_prompt_uses_given_car_and_track():
    p = build_prompt({}, setup_fields={}, car="Porsche 963 GTP", track="Monza")
    assert "Porsche 963 GTP" in p and "Monza" in p
