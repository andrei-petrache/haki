"""Body weight and the adaptive calorie target.

Weigh-ins: PUT and DELETE /weights/{day}, GET /weights. The target: GET
/targets/current, chosen with PUT /auth/me/goal. The arithmetic is in
app/adaptive.py; this module reads the data and keeps one TDEE estimate a
week (TdeeEstimate).

Weight is health data (GDPR Art. 9): everything here sits behind
settings.body_weight_enabled, off until users can consent, and no value
of it is ever logged.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import adaptive
from app.auth import CurrentUser, SessionDep
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.models import BodyWeight, Food, MealEntry, QuickEntry, TdeeEstimate, User
from app.schemas import (
    GoalIn,
    TargetResponse,
    UserResponse,
    WeightIn,
    WeightPoint,
    WeightResponse,
)

EARLIEST_DAY = date(2000, 1, 1)
# GET /weights returns at most a year
MAX_RANGE_DAYS = 366
DEFAULT_RANGE_DAYS = 90
# The trend line starts this long before the range shown, so it has settled
TREND_WARMUP_DAYS = 60


def require_enabled() -> None:
    """Off, the endpoints answer as if they did not exist."""
    if not settings.body_weight_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(tags=["body"], dependencies=[Depends(require_enabled)])


def server_today() -> date:
    return datetime.now(UTC).date()


def check_near_today(day: date) -> None:
    """The client's today may differ from the server's by a day (time zones
    run from -12 h to +14 h), never more: so no one can make estimates for
    weeks to come, which would break the chain of estimates."""
    if abs((day - server_today()).days) > 1:
        raise ApiError(ErrorCode.DATE_OUT_OF_RANGE)


def check_weigh_in_day(day: date) -> None:
    if not EARLIEST_DAY <= day <= server_today() + timedelta(days=1):
        raise ApiError(ErrorCode.DATE_OUT_OF_RANGE)


def own_weight(session: Session, user: User, day: date) -> BodyWeight | None:
    query = select(BodyWeight).where(
        BodyWeight.user_id == user.id, BodyWeight.measured_on == day
    )
    return session.scalar(query)


@router.put("/weights/{day}", response_model=WeightResponse)
def put_weight(
    day: date,
    data: WeightIn,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
) -> BodyWeight:
    """Record the day's weigh-in: 201 when new, 200 when it replaces one."""
    check_weigh_in_day(day)
    # Stored to 10 g; rounded here too, so the answer is what is stored
    weight = round(data.weight_kg, 2)
    row = own_weight(session, current_user, day)
    if row is not None:
        row.weight_kg = weight
        session.commit()
        return row
    row = BodyWeight(user_id=current_user.id, measured_on=day, weight_kg=weight)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        # Another request recorded the same day first: replace its value
        session.rollback()
        row = own_weight(session, current_user, day)
        if row is None:
            raise
        row.weight_kg = weight
        session.commit()
        return row
    response.status_code = status.HTTP_201_CREATED
    return row


@router.delete("/weights/{day}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weight(
    day: date, current_user: CurrentUser, session: SessionDep
) -> Response:
    row = own_weight(session, current_user, day)
    if row is None:
        raise ApiError(ErrorCode.WEIGHT_NOT_FOUND)
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/weights", response_model=list[WeightPoint])
def list_weights(
    current_user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[WeightPoint]:
    """The weigh-ins from `from` to `to` (both included), oldest first, each
    with the trend line. By default the last 90 days; at most a year."""
    end = end or server_today() + timedelta(days=1)
    start = start or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if not timedelta(0) <= end - start < timedelta(days=MAX_RANGE_DAYS):
        raise ApiError(ErrorCode.DATE_OUT_OF_RANGE)
    query = (
        select(BodyWeight.measured_on, BodyWeight.weight_kg)
        .where(
            BodyWeight.user_id == current_user.id,
            BodyWeight.measured_on.between(
                start - timedelta(days=TREND_WARMUP_DAYS), end
            ),
        )
        .order_by(BodyWeight.measured_on)
    )
    points = [(day, kg) for day, kg in session.execute(query)]
    line = dict(adaptive.trend(points))
    return [
        WeightPoint(
            measured_on=day,
            weight_kg=kg,
            trend_kg=round(line[day], 2),
            outlier=adaptive.is_outlier(kg, line[day]),
        )
        for day, kg in points
        if day >= start
    ]


@router.put("/auth/me/goal", response_model=UserResponse)
def set_goal(data: GoalIn, current_user: CurrentUser, session: SessionDep) -> User:
    """Choose the target: the user's own number, or the adaptive one with a
    goal in kg a week. The daily_calorie_target stays, as the fallback."""
    current_user.target_mode = data.target_mode
    goal = data.goal_kg_per_week
    current_user.goal_kg_per_week = None if goal is None else round(goal, 2)
    session.commit()
    return current_user


@router.get("/targets/current", response_model=TargetResponse)
def read_target(
    day: Annotated[date, Query(alias="date")],
    current_user: CurrentUser,
    session: SessionDep,
) -> TargetResponse:
    """The calorie target for the client's today. In adaptive mode the
    week's estimate is computed at the first read of the week, then kept."""
    check_near_today(day)
    return target_for(session, current_user, day, create=True)


def target_for(session: Session, user: User, day: date, create: bool) -> TargetResponse:
    """The target on `day`. Without `create`, a week with no estimate yet
    reads as still collecting (the user's own number)."""
    manual = user.daily_calorie_target
    if user.target_mode != "adaptive":
        return TargetResponse(
            target_mode=user.target_mode,
            status="manual",
            target_kcal=manual,
            goal_kg_per_week=user.goal_kg_per_week,
        )
    week_start = day - timedelta(days=day.weekday())
    found = weekly_estimate(session, user, week_start, create)
    if found is None:
        return TargetResponse(
            target_mode="adaptive",
            status="collecting",
            target_kcal=manual,
            week_start=week_start,
            goal_kg_per_week=user.goal_kg_per_week,
        )
    response = TargetResponse(
        target_mode="adaptive",
        status="collecting",
        target_kcal=manual,
        week_start=week_start,
        weigh_ins=found.weigh_ins,
        logged_days=found.logged_days,
        reasons=found.reasons.split(",") if found.reasons else [],
        trend_kg_per_week=found.slope_kg_per_week,
        goal_kg_per_week=user.goal_kg_per_week,
    )
    if found.tdee_kcal is None:
        return response
    # The target follows the goal the user has now, not the one stored
    target = adaptive.target(
        found.tdee_kcal, user.goal_kg_per_week, found.trend_weight_kg
    )
    return response.model_copy(
        update={
            "status": "adaptive",
            "target_kcal": target.kcal,
            "tdee_kcal": found.tdee_kcal,
            "floor_applied": target.floor_applied,
        }
    )


def daily_intake(
    session: Session, user: User, start: date, end: date
) -> dict[date, float]:
    """kcal eaten each day from `start` to `end`, foods and quick entries;
    days with nothing logged are absent."""
    meals = (
        select(
            MealEntry.eaten_on,
            func.sum(MealEntry.grams * Food.calories_per_100g / 100),
        )
        .join(Food, Food.id == MealEntry.food_id)
        .where(MealEntry.user_id == user.id, MealEntry.eaten_on.between(start, end))
        .group_by(MealEntry.eaten_on)
    )
    quick = (
        select(QuickEntry.eaten_on, func.sum(QuickEntry.calories))
        .where(QuickEntry.user_id == user.id, QuickEntry.eaten_on.between(start, end))
        .group_by(QuickEntry.eaten_on)
    )
    totals: dict[date, float] = defaultdict(float)
    for query in (meals, quick):
        for day, kcal in session.execute(query):
            totals[day] += float(kcal)
    return dict(totals)


def weekly_estimate(
    session: Session, user: User, week_start: date, create: bool
) -> TdeeEstimate | None:
    """The week's estimate; with `create`, computed and stored if missing.

    It looks at the 21 days before the week. The one it is smoothed
    against is the last estimate with a TDEE, if that is last week's; an
    older one, or none, starts afresh.
    """
    query = select(TdeeEstimate).where(
        TdeeEstimate.user_id == user.id, TdeeEstimate.week_start == week_start
    )
    found = session.scalar(query)
    if found is not None or not create:
        return found

    previous = session.scalar(
        select(TdeeEstimate)
        .where(
            TdeeEstimate.user_id == user.id,
            TdeeEstimate.week_start < week_start,
            TdeeEstimate.tdee_kcal.is_not(None),
        )
        .order_by(TdeeEstimate.week_start.desc())
        .limit(1)
    )
    previous_tdee = None
    if previous is not None and (week_start - previous.week_start).days <= 7:
        previous_tdee = previous.tdee_kcal
    end = week_start - timedelta(days=1)
    start = end - timedelta(days=adaptive.WINDOW_DAYS - 1)
    in_window = select(BodyWeight.measured_on, BodyWeight.weight_kg).where(
        BodyWeight.user_id == user.id, BodyWeight.measured_on.between(start, end)
    )
    weights = {day: kg for day, kg in session.execute(in_window)}
    reference = user.daily_calorie_target or previous_tdee
    result = adaptive.estimate(
        weights, daily_intake(session, user, start, end), end, reference, previous_tdee
    )

    # Two first reads at once both compute it; the second insert does nothing
    # and both return the row that won
    dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
    session.execute(
        dialect.insert(TdeeEstimate)
        .values(
            user_id=user.id,
            week_start=week_start,
            status=result.status,
            tdee_kcal=result.tdee_kcal,
            slope_kg_per_week=result.slope_kg_per_week,
            trend_weight_kg=result.trend_weight_kg,
            goal_kg_per_week=user.goal_kg_per_week,
            weigh_ins=result.weigh_ins,
            logged_days=result.logged_days,
            reasons=",".join(result.reasons),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "week_start"])
    )
    session.commit()
    return session.scalar(query)
