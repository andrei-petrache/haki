"""Golden numbers for the adaptive target (app/adaptive.py)."""

from datetime import date, timedelta

import pytest

from app.adaptive import (
    KCAL_PER_KG,
    MAX_WEEKLY_DROP,
    MAX_WEEKLY_RISE,
    estimate,
    is_outlier,
    slope,
    target,
    trend,
)

END = date(2026, 11, 15)  # a Sunday: the window is 26 Oct - 15 Nov
DAYS = [END - timedelta(days=n) for n in range(20, -1, -1)]  # 21 days, oldest first


def daily(start_kg: float, kg_per_week: float) -> dict[date, float]:
    """A weigh-in every day on a straight line."""
    return {day: start_kg + kg_per_week * i / 7 for i, day in enumerate(DAYS)}


def eating(kcal: float, days: list[date] = DAYS) -> dict[date, float]:
    return dict.fromkeys(days, kcal)


def test_a_stable_weight_means_the_tdee_is_what_was_eaten() -> None:
    result = estimate(daily(80, 0), eating(2300), END, 2300, None)

    assert result.status == "adaptive"
    assert result.tdee_kcal == 2300
    assert result.slope_kg_per_week == 0
    assert result.reasons == ()


def test_losing_half_a_kilo_a_week_on_2000_kcal_is_about_2550() -> None:
    result = estimate(daily(80, -0.5), eating(2000), END, 2000, None)

    assert result.slope_kg_per_week == pytest.approx(-0.5)
    assert result.tdee_kcal == 2550


def test_one_odd_weigh_in_barely_moves_the_slope() -> None:
    weights = daily(80, -0.5)
    weights[DAYS[10]] += 3  # a salty dinner, or the wrong scale

    result = estimate(weights, eating(2000), END, 2000, None)

    assert result.tdee_kcal == pytest.approx(2550, abs=25)


def test_partly_logged_days_are_left_out_not_read_as_zero() -> None:
    intake = eating(2300)
    for day in DAYS[::4]:
        intake[day] = 500  # breakfast only

    result = estimate(daily(80, 0), intake, END, 2300, None)

    assert result.tdee_kcal == 2300
    assert result.logged_days == 21 - len(DAYS[::4])


def test_half_the_target_also_counts_as_a_partial_day() -> None:
    intake = eating(2300)
    intake[DAYS[0]] = 1100  # above 800, under half of a 2400 target

    result = estimate(daily(80, 0), intake, END, 2400, None)

    assert result.logged_days == 20


def test_the_new_estimate_is_half_the_new_data_half_the_last_one() -> None:
    result = estimate(daily(80, 0), eating(2300), END, 2300, 2250)

    assert result.tdee_kcal == 2275


@pytest.mark.parametrize(
    ("eaten", "previous", "expected"),
    [
        (1500, 2500, 2500 - MAX_WEEKLY_DROP),  # under-logging falls slowly
        (3500, 2500, 2500 + MAX_WEEKLY_RISE),
    ],
)
def test_a_week_moves_the_estimate_by_at_most_the_clamp(
    eaten: float, previous: int, expected: int
) -> None:
    result = estimate(daily(80, 0), eating(eaten), END, 2500, previous)

    assert result.tdee_kcal == expected


def test_the_tdee_stays_within_its_bounds() -> None:
    result = estimate(daily(80, 0), eating(900), END, None, None)

    assert result.tdee_kcal == 1200


@pytest.mark.parametrize(
    ("weights", "intake", "reasons"),
    [
        # Ten days of data only
        (
            {d: 80.0 for d in DAYS[-10:]},
            eating(2300, DAYS[-10:]),
            ("few_days",),
        ),
        # Weighed once a week: too few, and one at each end
        (
            {d: 80.0 for d in DAYS[::7]},
            eating(2300),
            ("few_weigh_ins", "no_weigh_ins_at_start", "no_weigh_ins_at_end"),
        ),
        # Eight weigh-ins, all in the last week
        (
            {d: 80.0 for d in DAYS[-8:]} | {DAYS[0]: 80.0, DAYS[6]: 80.0},
            eating(2300, DAYS[:9]),
            ("few_logged_days",),
        ),
        # Weighed every day of the first two weeks, then stopped
        (
            {d: 80.0 for d in DAYS[:14]},
            eating(2300),
            ("no_weigh_ins_at_end",),
        ),
    ],
)
def test_too_little_data_is_still_collecting(
    weights: dict[date, float], intake: dict[date, float], reasons: tuple[str, ...]
) -> None:
    result = estimate(weights, intake, END, 2300, None)

    assert result.status == "collecting"
    assert result.tdee_kcal is None
    assert result.reasons == reasons


def test_weigh_ins_bunched_at_the_end_are_still_collecting() -> None:
    # Ten weigh-ins, no gap over a week, but only one in the first week
    weights = {DAYS[0]: 80.0, DAYS[7]: 80.0, DAYS[13]: 80.0}
    weights |= {d: 80.0 for d in DAYS[14:]}

    result = estimate(weights, eating(2300), END, 2300, None)

    assert result.weigh_ins == 10
    assert result.reasons == ("no_weigh_ins_at_start",)


def test_a_gap_of_more_than_a_week_starts_the_window_again() -> None:
    # Two weigh-ins at the start, eight days without, then nine days
    weights = {DAYS[0]: 90.0, DAYS[1]: 90.0} | {d: 80.0 for d in DAYS[-9:]}

    result = estimate(weights, eating(2300), END, 2300, None)

    # The 10 kg before the gap would have made a huge slope
    assert result.status == "collecting"
    assert result.weigh_ins == 9
    assert "few_days" in result.reasons


def test_days_outside_the_window_are_ignored() -> None:
    weights = daily(80, 0) | {END - timedelta(days=30): 100.0, END + timedelta(1): 60}

    result = estimate(weights, eating(2300), END, 2300, None)

    assert result.tdee_kcal == 2300
    assert result.weigh_ins == 21


def test_the_target_follows_the_goal() -> None:
    assert target(2550, -0.5, 80).kcal == 2000
    assert target(2550, 0.25, 80).kcal == 2830  # 2550 + 275
    assert target(2550, None, 80).kcal == 2550


def test_a_loss_goal_is_capped_at_one_percent_of_body_weight() -> None:
    # 1 kg a week asked for at 55 kg: 0.55 kg a week given
    result = target(2000, -1.0, 55)

    assert result.kcal == round((2000 - 0.55 * KCAL_PER_KG / 7) / 10) * 10
    assert not result.floor_applied


def test_the_floor_wins_and_says_so() -> None:
    result = target(1700, -1.0, 100)

    assert result.kcal == 1200
    assert result.floor_applied


def test_never_more_than_1000_under_the_tdee() -> None:
    result = target(3500, -1.0, 150)

    assert result.kcal == 2500
    assert result.floor_applied


def test_the_trend_lags_and_flags_an_outlier() -> None:
    points = sorted(daily(80, 0).items())
    points[10] = (points[10][0], 83.0)

    line = dict(trend(points))

    assert line[points[9][0]] == pytest.approx(80)
    assert is_outlier(83.0, line[points[10][0]])
    assert not is_outlier(80.0, line[points[11][0]])


def test_the_slope_ignores_days_without_weigh_ins() -> None:
    points = [(DAYS[0], 80.0), (DAYS[7], 79.5), (DAYS[14], 79.0)]

    assert slope(points) * 7 == pytest.approx(-0.5)
