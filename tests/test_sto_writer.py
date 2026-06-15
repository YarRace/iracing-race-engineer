from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes, build_setup_sheet


def test_delta_becomes_manual_change_list():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    changes = build_manual_changes(setup, {key: "155 kPa"})
    assert len(changes) == 1
    ch = changes[0]
    assert ch["field"] == key
    assert ch["from"] == setup["fields"][key]   # "152 kPa"
    assert ch["to"] == "155 kPa"


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
