from ire.setup.sto_reader import read_sto

def test_reads_known_fields_from_fixture():
    s = read_sto("tests/fixtures/sample_setup.json")
    assert "fields" in s and len(s["fields"]) > 0
    # поля адресуются плоским путём, напр. "TiresAero.LeftFront.StartingPressure"
    assert any("pressure" in k.lower() for k in s["fields"])
    assert s["fields"]["TiresAero.LeftFront.StartingPressure"] == "152 kPa"
