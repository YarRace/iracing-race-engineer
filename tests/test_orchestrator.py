import json
from ire import orchestrator as orch

def test_analyze_stint_produces_result(monkeypatch):
    frames = [json.loads(l) for l in open("tests/fixtures/sample_stint.jsonl", encoding="utf-8")]
    monkeypatch.setattr(orch, "explain",
        lambda sym, setup, **kw: {"driving": ["ok"], "setup_changes": [], "delta": {}})
    res = orch.analyze_stint(frames, setup_path="tests/fixtures/sample_setup.json",
                             conditions={"track_temp": 40})
    assert "symptoms" in res and res["explanation"]["driving"] == ["ok"]


def test_identity_reaches_explainer(monkeypatch):
    """Машина и трасса должны доезжать из живого цикла до промпта, иначе
    разбор идёт не про ту машину."""
    seen = {}

    def fake_explain(symptoms, fields, car=None, track=None):
        seen["car"], seen["track"] = car, track
        return {"driving": [], "setup_changes": [], "delta": {}}

    monkeypatch.setattr(orch, "explain", fake_explain)
    frames = [json.loads(l) for l in open("tests/fixtures/sample_stint.jsonl", encoding="utf-8")]
    orch.analyze_stint(frames, setup_path="tests/fixtures/sample_setup.json",
                       conditions={"track_temp": 30.0},
                       identity={"car": "Porsche 963 GTP", "track_display": "Monza"})
    assert seen == {"car": "Porsche 963 GTP", "track": "Monza"}
