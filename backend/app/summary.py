from fastapi import APIRouter

from app.auth import CurrentUser, SessionDep
from app.entries import DayQuery, entries_for_day, nutrients_for
from app.models import MEAL_TYPES
from app.schemas import DailySummary, Nutrients

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("", response_model=DailySummary)
def daily_summary(
    day: DayQuery, current_user: CurrentUser, session: SessionDep
) -> DailySummary:
    """Totals for one day, overall and per meal, against the calorie target."""
    meals = {meal: Nutrients() for meal in MEAL_TYPES}
    for entry in entries_for_day(session, current_user, day):
        meals[entry.meal_type] += nutrients_for(entry.food, entry.grams)
    totals = sum(meals.values(), Nutrients())

    target = current_user.daily_calorie_target
    # Negative when the user ate more than the target
    remaining = None if target is None else round(target - totals.calories, 1)
    return DailySummary(
        eaten_on=day,
        totals=totals,
        meals=meals,
        daily_calorie_target=target,
        calories_remaining=remaining,
    )
