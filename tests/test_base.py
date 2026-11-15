from src.base import base_suitability

SUNNY = {"illumination_mean": 0.45, "earth_visibility_mean": 0.8, "psr_fraction": 0.0}


def test_flat_sunny_window_meets_habitat_full():
    r = base_suitability([0.8, 0.15, 0.05], SUNNY)
    assert r["landing_habitat"]["meets"] and r["rover_traverse"]["meets"]
    assert r["power_comms"]["meets"] and r["habitat_full"]["meets"]
    assert not r["isru_ice"]["meets"]


def test_steep_window_meets_no_topography_profile():
    r = base_suitability([0.0037, 0.2084, 0.7879], SUNNY)
    assert not r["landing_habitat"]["meets"] and not r["rover_traverse"]["meets"]
    assert not r["habitat_full"]["meets"]
    assert r["power_comms"]["meets"]  # la iluminación no depende de la pendiente


def test_flat_but_dark_window_is_not_full_habitat():
    dark = {"illumination_mean": 0.05, "earth_visibility_mean": 0.9, "psr_fraction": 0.4}
    r = base_suitability([0.9, 0.1, 0.0], dark)
    assert r["landing_habitat"]["meets"] and not r["power_comms"]["meets"]
    assert not r["habitat_full"]["meets"] and r["isru_ice"]["meets"]


def test_missing_data_gives_none_not_false():
    r = base_suitability([], None)
    assert r["landing_habitat"]["meets"] is None
    assert r["power_comms"]["meets"] is None
    r2 = base_suitability([0.8, 0.15, 0.05], None)
    assert r2["landing_habitat"]["meets"] is True and r2["habitat_full"]["meets"] is None
