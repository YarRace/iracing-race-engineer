from ire.metrics.symptoms import build_symptoms
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes, build_setup_sheet
from ire.explainer.explainer import explain

def analyze_stint(frames, setup_path, conditions):
    symptoms = build_symptoms(frames, conditions)
    setup = read_sto(setup_path)               # источник: CarSetup JSON (или ir["CarSetup"])
    explanation = explain(symptoms, setup["fields"])
    manual_changes = []
    setup_sheet = None
    if explanation.get("delta"):               # .sto не пишем — дельта для ручного ввода
        manual_changes = build_manual_changes(
            setup, explanation["delta"], explanation.get("setup_changes"))
        setup_sheet = build_setup_sheet(setup, explanation["delta"])  # полный лист-шпаргалка
    return {"symptoms": symptoms, "explanation": explanation,
            "manual_changes": manual_changes, "setup_sheet": setup_sheet}
