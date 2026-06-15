import json
from ire.metrics.symptoms import build_symptoms

def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]

def test_symptoms_from_real_stint():
    frames = _load("tests/fixtures/sample_stint.jsonl")
    s = build_symptoms(frames, conditions={"track_temp": frames[0]["track_temp"]})
    for key in ("tire", "balance", "suspension", "inputs", "consistency", "conditions"):
        assert key in s
    json.dump(s, open("tests/fixtures/sample_symptoms.json", "w"), indent=2)
