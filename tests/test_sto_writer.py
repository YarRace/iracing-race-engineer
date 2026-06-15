from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_manual_changes


def test_delta_becomes_manual_change_list():
    setup = read_sto("tests/fixtures/sample_setup.json")
    key = "TiresAero.LeftFront.StartingPressure"
    changes = build_manual_changes(setup, {key: "155 kPa"})
    assert len(changes) == 1
    ch = changes[0]
    assert ch["field"] == key
    assert ch["from"] == setup["fields"][key]   # "152 kPa"
    assert ch["to"] == "155 kPa"
