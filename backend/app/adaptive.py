"""The adaptive calorie target: arithmetic only, no database.

How much a user burns a day (their TDEE) follows from what they ate and
how their weight moved: eating 2000 kcal a day while losing 0.5 kg a week
means burning about 2000 + 0.5 x 7700 / 7 = 2550. The target is then the
TDEE plus or minus what the user's goal asks for. app/body.py reads the
data and stores one estimate per week; everything here is a pure function
of its arguments, so it is tested with plain numbers (tests/test_adaptive.py).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, floor
from statistics import mean, median
from typing import Literal

# Energy in 1 kg of body fat, roughly. The first weeks of a diet lose
# water too, which this overstates as fat; the collecting weeks soften it.
KCAL_PER_KG = 7700

# The estimate looks at the 21 days before the week it is for
WINDOW_DAYS = 21
# Below any of these, the estimate is still "collecting" (see estimate())
MIN_DAYS = 14
MIN_WEIGH_INS = 8
MIN_LOGGED_DAYS = 10
# Weigh-ins at both ends: eight in one week give a slope from noise
END_DAYS = 7
MIN_WEIGH_INS_AT_EACH_END = 2
# No weigh-in for longer than this starts the window again after the gap
MAX_GAP_DAYS = 7

# A day with less than this was not logged in full: left out, never read
# as a day of eating nothing (which would drag the TDEE down)
PARTIAL_DAY_KCAL = 800
PARTIAL_DAY_SHARE = 0.5

# Week to week, the new estimate is half the new data, half the last one,
# and moves at most this far. It may rise faster than it falls: a user who
# logs less than they eat would otherwise ratchet their target down.
SMOOTHING = 0.5
MAX_WEEKLY_DROP = 100
MAX_WEEKLY_RISE = 150
TDEE_MIN = 1200
TDEE_MAX = 5000

# The target never goes below the floor, nor more than MAX_BELOW_TDEE under
# the TDEE, and a weight-loss goal is capped at 1% of body weight a week
TARGET_FLOOR = 1200
MAX_BELOW_TDEE = 1000
MAX_LOSS_SHARE_PER_WEEK = 0.01

# The chart's trend line: an exponentially weighted moving average
TREND_ALPHA = 0.1
# A weigh-in this far from the trend is flagged (kept, never dropped)
OUTLIER_SHARE = 0.02

Reason = Literal[
    "few_days",
    "few_weigh_ins",
    "few_logged_days",
    "no_weigh_ins_at_start",
    "no_weigh_ins_at_end",
]
Status = Literal["collecting", "adaptive"]


@dataclass(frozen=True)
class Estimate:
    """One week's estimate. tdee_kcal is None while still collecting."""

    status: Status
    tdee_kcal: int | None
    # Fitted from the weigh-ins; positive when gaining
    slope_kg_per_week: float | None
    # The trend at the last weigh-in, for the 1% cap on a loss goal
    trend_weight_kg: float | None
    weigh_ins: int
    logged_days: int
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class Target:
    kcal: int
    # True when the floor, not the goal, set the number: the UI says so
    floor_applied: bool


def trend(points: Sequence[tuple[date, float]]) -> list[tuple[date, float]]:
    """The trend at each weigh-in: an EWMA over every day, the days without
    a weigh-in filled by a straight line between their neighbours. For the
    chart only; the slope comes from the weigh-ins themselves (slope())."""
    points = sorted(points)
    if not points:
        return []
    result = [(points[0][0], points[0][1])]
    level = points[0][1]
    for (before, w_before), (after, w_after) in zip(points, points[1:], strict=False):
        days = (after - before).days
        for step in range(1, days + 1):
            weight = w_before + (w_after - w_before) * step / days
            level += TREND_ALPHA * (weight - level)
        result.append((after, level))
    return result


def is_outlier(weight: float, trend_weight: float) -> bool:
    return abs(weight - trend_weight) > OUTLIER_SHARE * trend_weight


def slope(points: Sequence[tuple[date, float]]) -> float:
    """kg per day, by Theil-Sen: the median of the slopes between every two
    weigh-ins. One odd weigh-in moves it little, unlike a least-squares fit,
    and it has no lag, unlike the trend line."""
    slopes = [
        (w2 - w1) / (d2 - d1).days
        for i, (d1, w1) in enumerate(points)
        for d2, w2 in points[i + 1 :]
        if d2 != d1
    ]
    return median(slopes)


def estimate(
    weights: Mapping[date, float],
    intake: Mapping[date, float],
    end: date,
    reference_kcal: float | None,
    previous_tdee: int | None,
) -> Estimate:
    """The TDEE from the WINDOW_DAYS ending on `end` (inclusive).

    `weights` and `intake` (kcal eaten per day) may hold days outside the
    window; they are ignored. `reference_kcal` is the target the user has
    now, for telling a partly logged day; `previous_tdee` the last estimate,
    None to start afresh.
    """
    start = end - timedelta(days=WINDOW_DAYS - 1)
    points = sorted((day, kg) for day, kg in weights.items() if start <= day <= end)
    # After a gap without weigh-ins, only what comes after it counts
    for (before, _), (after, _) in zip(points, points[1:], strict=False):
        if (after - before).days > MAX_GAP_DAYS:
            start = after
    if points and (end - points[-1][0]).days > MAX_GAP_DAYS:
        start = end + timedelta(days=1)
    points = [(day, kg) for day, kg in points if day >= start]
    first = points[0][0] if points else end + timedelta(days=1)

    threshold = PARTIAL_DAY_KCAL
    if reference_kcal is not None:
        threshold = max(threshold, PARTIAL_DAY_SHARE * reference_kcal)
    logged = [kcal for day, kcal in intake.items() if first <= day <= end]
    logged = [kcal for kcal in logged if kcal >= threshold]

    reasons: list[Reason] = []
    if (end - first).days + 1 < MIN_DAYS:
        reasons.append("few_days")
    if len(points) < MIN_WEIGH_INS:
        reasons.append("few_weigh_ins")
    if len(logged) < MIN_LOGGED_DAYS:
        reasons.append("few_logged_days")
    early = [day for day, _ in points if (day - first).days < END_DAYS]
    late = [day for day, _ in points if (end - day).days < END_DAYS]
    if len(early) < MIN_WEIGH_INS_AT_EACH_END:
        reasons.append("no_weigh_ins_at_start")
    if len(late) < MIN_WEIGH_INS_AT_EACH_END:
        reasons.append("no_weigh_ins_at_end")
    trend_weight = trend(points)[-1][1] if points else None
    if reasons:
        return Estimate(
            status="collecting",
            tdee_kcal=None,
            slope_kg_per_week=None,
            trend_weight_kg=trend_weight,
            weigh_ins=len(points),
            logged_days=len(logged),
            reasons=tuple(reasons),
        )

    per_day = slope(points)
    tdee = mean(logged) - per_day * KCAL_PER_KG
    if previous_tdee is not None:
        tdee = SMOOTHING * tdee + (1 - SMOOTHING) * previous_tdee
        tdee = min(
            max(tdee, previous_tdee - MAX_WEEKLY_DROP), previous_tdee + MAX_WEEKLY_RISE
        )
    tdee = min(max(tdee, TDEE_MIN), TDEE_MAX)
    return Estimate(
        status="adaptive",
        tdee_kcal=round(tdee),
        slope_kg_per_week=round(per_day * 7, 3),
        trend_weight_kg=trend_weight,
        weigh_ins=len(points),
        logged_days=len(logged),
        reasons=(),
    )


def target(
    tdee_kcal: int, goal_kg_per_week: float | None, trend_weight_kg: float | None
) -> Target:
    """The daily target for a TDEE and a goal (kg a week, negative to lose),
    rounded to 10 kcal."""
    rate = goal_kg_per_week or 0.0
    if rate < 0 and trend_weight_kg is not None:
        rate = max(rate, -MAX_LOSS_SHARE_PER_WEEK * trend_weight_kg)
    kcal = tdee_kcal + rate * KCAL_PER_KG / 7
    lowest = max(TARGET_FLOOR, tdee_kcal - MAX_BELOW_TDEE)
    if kcal < lowest:
        # Rounded up, so the floor is never crossed
        return Target(kcal=ceil(lowest / 10) * 10, floor_applied=True)
    # Half up (2825 → 2830), not round()'s half to even
    return Target(kcal=floor(kcal / 10 + 0.5) * 10, floor_applied=False)
