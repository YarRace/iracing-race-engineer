from ire.collector.stint_recorder import StintDetector

def test_stint_closes_when_entering_pits():
    d = StintDetector()
    assert d.update(on_track=True) == "running"
    assert d.update(on_track=True) == "running"
    assert d.update(on_track=False) == "closed"   # заехал в бокс → стинт закрыт
    assert d.update(on_track=False) == "idle"
