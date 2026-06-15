from ire.metrics.symptoms import build_symptoms
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes
from ire.explainer.explainer import explain

def analyze_stint(frames, setup_path, conditions):
    symptoms = build_symptoms(frames, conditions)
    setup = read_sto(setup_path)               # источник: CarSetup JSON (или ir["CarSetup"])
    explanation = explain(symptoms, setup["fields"])
    manual_changes = []
    if explanation.get("delta"):               # .sto не пишем — дельта для ручного ввода
        manual_changes = build_manual_changes(setup, explanation["delta"])
    return {"symptoms": symptoms, "explanation": explanation, "manual_changes": manual_changes}
