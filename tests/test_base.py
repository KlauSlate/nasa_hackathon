from src.base import base_suitability


def test_flat_window_meets_both():
    r = base_suitability([0.8, 0.15, 0.05])
    assert r["landing_habitat"]["fraction"] == 0.8 and r["landing_habitat"]["meets"]
    assert r["rover_traverse"]["fraction"] == 0.95 and r["rover_traverse"]["meets"]


def test_steep_window_meets_neither():
    r = base_suitability([0.0037, 0.2084, 0.7879])
    assert not r["landing_habitat"]["meets"]
    assert not r["rover_traverse"]["meets"]


def test_missing_classes():
    assert base_suitability([])["landing_habitat"]["meets"] is None
