from ire.metrics.symptoms import build_symptoms
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes, build_setup_sheet, build_setup_tabs
from ire.explainer.explainer import explain

def analyze_stint(frames, setup_path, conditions, identity=None):
    """identity — снимок сессии (трасса/машина) из session_identity().

    Без него разбор шёл про машину по умолчанию: на Porsche в Монце модель
    получала в промпте «Cadillac GTP, Watkins Glen» и советовала сетап
    не от той машины."""
    symptoms = build_symptoms(frames, conditions)
    setup = read_sto(setup_path)               # источник: CarSetup JSON (или ir["CarSetup"])
    ident = identity or {}
    explanation = explain(symptoms, setup["fields"],
                          car=ident.get("car"),
                          track=ident.get("track_display") or ident.get("track"))
    manual_changes = []
    setup_sheet = None
    delta = explanation.get("delta") or {}
    if delta:                                  # .sto не пишем — дельта для ручного ввода
        manual_changes = build_manual_changes(
            setup, delta, explanation.get("setup_changes"))
        setup_sheet = build_setup_sheet(setup, delta, car=ident.get("car"))  # полный лист-шпаргалка (для скачивания)
    # вкладки — как экран настроек iRacing (показываем всегда, даже без правок)
    setup_tabs = build_setup_tabs(setup, delta)
    return {"symptoms": symptoms, "explanation": explanation,
            "manual_changes": manual_changes, "setup_sheet": setup_sheet,
            "setup_tabs": setup_tabs}
