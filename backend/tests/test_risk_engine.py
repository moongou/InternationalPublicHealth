import pytest

from app.risk_engine import calculate_passenger_risk, calculate_risk, risk_level


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0, "blue"), (39.9, "blue"), (40, "yellow"), (59.9, "yellow"), (60, "orange"), (79.9, "orange"), (80, "red"), (100, "red")],
)
def test_risk_level_boundaries(score, expected):
    assert risk_level(score) == expected


def test_weighted_risk_inverts_response_capacity():
    factors = {"severity": 90, "transmission": 80, "scale": 70, "travel": 60, "transit": 50, "capacity": 20}
    score, level = calculate_risk(factors)
    assert score == 75.0
    assert level == "orange"


def test_passenger_risk_adds_missing_declaration_and_transit():
    result = calculate_passenger_risk([("测试国", 75)], has_health_declaration=False, transit_count=2)
    assert result.score == 93
    assert result.level == "red"
    assert len(result.advice) >= 3


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        calculate_risk({}, {"severity": 0.2})
