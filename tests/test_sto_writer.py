from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes, build_setup_sheet, build_setup_tabs


def test_delta_becomes_manual_change_list():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    changes = build_manual_changes(setup, {key: "155 kPa"})
    assert len(changes) == 1
    ch = changes[0]
    assert ch["field"] == key
    assert ch["from"] == setup["fields"][key]   # "152 kPa"
    assert ch["to"] == "155 kPa"


def test_manual_changes_include_why_from_setup_changes():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    setup_changes = [{"field": key, "from": "152 kPa", "to": "148 kPa", "why": "против недоруля"}]
    changes = build_manual_changes(setup, {key: "148 kPa"}, setup_changes)
    assert changes[0]["why"] == "против недоруля"


def test_setup_sheet_lists_all_fields_and_marks_changes():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    sheet = build_setup_sheet(setup, {key: "148 kPa"})
    # все поля присутствуют (лист полный)
    assert len(sheet.splitlines()) > len(setup["fields"])
    # изменённое поле помечено новым значением и старым в скобках
    assert "148 kPa   <- ИЗМЕНИТЬ (было 152 kPa)" in sheet
    # неизменённое поле выводится как есть
    assert "Camber: -2.9 deg" in sheet


def test_setup_tabs_grouped_by_section_with_changes():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    tabs = build_setup_tabs(setup, {key: "148 kPa"})
    sections = [t["section"] for t in tabs]
    assert sections == ["TiresAero", "Chassis", "BrakesDriveUnit"]   # порядок как в CarSetup
    tires = tabs[0]
    assert tires["title"] == "Шины и аэро" and tires["changed"] == 1
    # находим изменённую строку
    lf = next(g for g in tires["groups"] if g["group"] == "LeftFront")
    row = next(r for r in lf["rows"] if r["name"] == "StartingPressure")
    assert row["changed"] is True and row["to"] == "148 kPa"
    assert row["value"] == setup["fields"][key]
    # UpdateCount (скаляр верхнего уровня) во вкладки не попадает
    assert all(t["section"] != "UpdateCount" for t in tabs)


def test_setup_tabs_no_delta_all_unchanged():
    setup = read_sto("tests/fixtures/sample_setup.json")
    tabs = build_setup_tabs(setup, {})
    assert all(t["changed"] == 0 for t in tabs)
    assert all(not r["changed"] for t in tabs for g in t["groups"] for r in g["rows"])
