"""The weekly dashboard: one week's food against the target, training volume
and, with consent, the body-weight trend, in one request.

GET /dashboard/week?start=<any day of the week> reads Monday to Sunday of
that week, and the totals of the week before for comparison. Read-only: it
never computes or stores a TDEE estimate (only /targets/current does).
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import adaptive
from app.auth import CurrentUser, SessionDep
from app.body import TREND_WARMUP_DAYS, server_today, target_for
from app.config import settings
from app.consent import has_consent
from app.errors import ApiError, ErrorCode
from app.models import (
    BodyWeight,
    CatalogExercise,
    Exercise,
    Food,
    MealEntry,
    QuickEntry,
    User,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

EARLIEST_DAY = date(2000, 1, 1)
# Exercises not copied from the catalog have no muscle to count under
OTHER = "other"


class DayTotals(BaseModel):
    date: date
    kcal: float
    protein: float
    carbs: float
    fat: float
    target_kcal: int | None
    # Anything logged that day, food or quick entry
    logged: bool
    workouts: int
    sets: int
    reps: int
    volume_kg: float


class WeekTotals(BaseModel):
    kcal: float
    protein: float
    carbs: float
    fat: float
    days_logged: int
    # Over the days with something logged; null when there are none
    avg_kcal: float | None
    workouts: int
    sets: int
    reps: int
    volume_kg: float


class ThisWeekTotals(WeekTotals):
    # The volume split over each exercise's primary muscles (catalog names)
    volume_by_muscle: dict[str, float]


class BodyWeightWeek(BaseModel):
    weigh_ins: int
    start_trend_kg: float | None
    end_trend_kg: float | None
    change_kg: float | None


class WeekResponse(BaseModel):
    week_start: date
    days: list[DayTotals]
    totals: ThisWeekTotals
    previous_week: WeekTotals
    # Only with body weight on and its consent given; null otherwise
    body_weight: BodyWeightWeek | None


def intake(
    session: Session, user: User, start: date, end: date
) -> dict[date, dict[str, float]]:
    """kcal and macros eaten each day from `start` to `end`, foods and quick
    entries together; days with nothing logged are absent."""
    share = MealEntry.grams / 100
    meals = (
        select(
            MealEntry.eaten_on,
            func.sum(share * Food.calories_per_100g),
            func.sum(share * Food.protein_per_100g),
            func.sum(share * Food.carbs_per_100g),
            func.sum(share * Food.fat_per_100g),
        )
        .join(Food, Food.id == MealEntry.food_id)
        .where(MealEntry.user_id == user.id, MealEntry.eaten_on.between(start, end))
        .group_by(MealEntry.eaten_on)
    )
    quick = (
        select(
            QuickEntry.eaten_on,
            func.sum(QuickEntry.calories),
            func.sum(QuickEntry.protein),
            func.sum(QuickEntry.carbs),
            func.sum(QuickEntry.fat),
        )
        .where(QuickEntry.user_id == user.id, QuickEntry.eaten_on.between(start, end))
        .group_by(QuickEntry.eaten_on)
    )
    days: dict[date, dict[str, float]] = {}
    for query in (meals, quick):
        for day, kcal, protein, carbs, fat in session.execute(query):
            totals = days.setdefault(
                day, {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
            )
            totals["kcal"] += float(kcal or 0)
            totals["protein"] += float(protein or 0)
            totals["carbs"] += float(carbs or 0)
            totals["fat"] += float(fat or 0)
    return days


class Training:
    """Workouts, sets, reps and volume per day, and volume per muscle."""

    def __init__(self, session: Session, user: User, start: date, end: date) -> None:
        self.workouts: dict[date, int] = defaultdict(int)
        self.sets: dict[date, int] = defaultdict(int)
        self.reps: dict[date, int] = defaultdict(int)
        self.volume: dict[date, float] = defaultdict(float)
        self.by_muscle: dict[str, float] = defaultdict(float)
        in_range = (
            Workout.user_id == user.id,
            Workout.performed_on.between(start, end),
        )
        for day, count in session.execute(
            select(Workout.performed_on, func.count())
            .where(*in_range)
            .group_by(Workout.performed_on)
        ):
            self.workouts[day] = count
        rows = session.execute(
            select(
                Workout.performed_on,
                WorkoutSet.reps,
                WorkoutSet.weight_kg,
                CatalogExercise.primary_muscles,
            )
            .join(WorkoutExercise, WorkoutExercise.id == WorkoutSet.workout_exercise_id)
            .join(Workout, Workout.id == WorkoutExercise.workout_id)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .outerjoin(
                CatalogExercise, CatalogExercise.id == Exercise.catalog_exercise_id
            )
            .where(*in_range)
        )
        for day, reps, weight, muscles in rows:
            volume = reps * weight
            self.sets[day] += 1
            self.reps[day] += reps
            self.volume[day] += volume
            # Split evenly, so the muscles add up to the week's volume
            names = muscles or [OTHER]
            for muscle in names:
                self.by_muscle[muscle] += volume / len(names)


def week_totals(
    days: list[date], eaten: dict[date, dict[str, float]], training: Training
) -> dict[str, float | int | None]:
    logged = [eaten[day] for day in days if day in eaten]
    kcal = sum(day["kcal"] for day in logged)
    return {
        "kcal": round(kcal, 1),
        "protein": round(sum(day["protein"] for day in logged), 1),
        "carbs": round(sum(day["carbs"] for day in logged), 1),
        "fat": round(sum(day["fat"] for day in logged), 1),
        "days_logged": len(logged),
        "avg_kcal": round(kcal / len(logged), 1) if logged else None,
        "workouts": sum(training.workouts[day] for day in days),
        "sets": sum(training.sets[day] for day in days),
        "reps": sum(training.reps[day] for day in days),
        "volume_kg": round(sum(training.volume[day] for day in days), 1),
    }


def week_target(session: Session, user: User, monday: date) -> int | None:
    """The target of that week, as /summary gives it; never creates an
    estimate."""
    if not settings.body_weight_enabled:
        return user.daily_calorie_target
    return target_for(session, user, monday, create=False).target_kcal


def body_weight_week(
    session: Session, user: User, monday: date, sunday: date
) -> BodyWeightWeek | None:
    if not settings.body_weight_enabled or not has_consent(session, user):
        return None
    query = (
        select(BodyWeight.measured_on, BodyWeight.weight_kg)
        .where(
            BodyWeight.user_id == user.id,
            BodyWeight.measured_on.between(
                monday - timedelta(days=TREND_WARMUP_DAYS), sunday
            ),
        )
        .order_by(BodyWeight.measured_on)
    )
    points = [(day, kg) for day, kg in session.execute(query)]
    line = [(day, kg) for day, kg in adaptive.trend(points) if day >= monday]
    if not line:
        return BodyWeightWeek(
            weigh_ins=0, start_trend_kg=None, end_trend_kg=None, change_kg=None
        )
    start, end = round(line[0][1], 2), round(line[-1][1], 2)
    return BodyWeightWeek(
        weigh_ins=len(line),
        start_trend_kg=start,
        end_trend_kg=end,
        change_kg=round(end - start, 2),
    )


@router.get("/week", response_model=WeekResponse)
def read_week(
    start: Annotated[date, Query()],
    current_user: CurrentUser,
    session: SessionDep,
) -> WeekResponse:
    """The week that holds `start` (any day of it), Monday to Sunday."""
    if not EARLIEST_DAY <= start <= server_today() + timedelta(days=7):
        raise ApiError(ErrorCode.DATE_OUT_OF_RANGE)
    monday = start - timedelta(days=start.weekday())
    sunday = monday + timedelta(days=6)
    previous = monday - timedelta(days=7)
    days = [monday + timedelta(days=n) for n in range(7)]
    previous_days = [previous + timedelta(days=n) for n in range(7)]

    eaten = intake(session, current_user, previous, sunday)
    training = Training(session, current_user, monday, sunday)
    previous_training = Training(session, current_user, previous, monday - timedelta(1))
    target = week_target(session, current_user, monday)

    return WeekResponse(
        week_start=monday,
        days=[
            DayTotals(
                date=day,
                kcal=round(eaten.get(day, {}).get("kcal", 0.0), 1),
                protein=round(eaten.get(day, {}).get("protein", 0.0), 1),
                carbs=round(eaten.get(day, {}).get("carbs", 0.0), 1),
                fat=round(eaten.get(day, {}).get("fat", 0.0), 1),
                target_kcal=target,
                logged=day in eaten,
                workouts=training.workouts[day],
                sets=training.sets[day],
                reps=training.reps[day],
                volume_kg=round(training.volume[day], 1),
            )
            for day in days
        ],
        totals=ThisWeekTotals(
            **week_totals(days, eaten, training),
            volume_by_muscle={
                muscle: round(volume, 1)
                for muscle, volume in sorted(training.by_muscle.items())
            },
        ),
        previous_week=WeekTotals(
            **week_totals(previous_days, eaten, previous_training)
        ),
        body_weight=body_weight_week(session, current_user, monday, sunday),
    )
