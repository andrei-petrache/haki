from fastapi import APIRouter

from app.auth import CurrentUser, SessionDep
from app.body import server_today, target_for
from app.config import settings
from app.entries import DayQuery, entries_for_day, nutrients_for, quick_entries_for
from app.models import MEAL_TYPES
from app.schemas import DailySummary, Nutrients

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("", response_model=DailySummary)
def daily_summary(
    day: DayQuery, current_user: CurrentUser, session: SessionDep
) -> DailySummary:
    """Totals for one day, overall and per meal, against the calorie target.
    Quick entries count like any other."""
    meals = {meal: Nutrients() for meal in MEAL_TYPES}
    for entry in entries_for_day(session, current_user, day):
        meals[entry.meal_type] += nutrients_for(entry.food, entry.grams)
    for quick in quick_entries_for(session, current_user, day):
        meals[quick.meal_type] += Nutrients(
            calories=quick.calories,
            protein=quick.protein,
            carbs=quick.carbs,
            fat=quick.fat,
        )
    totals = sum(meals.values(), Nutrients())

    target = current_user.daily_calorie_target
    if settings.body_weight_enabled:
        # The adaptive target when the user chose it. Only a day near today
        # may compute the week's estimate (see check_near_today); another
        # day reads the one it has, or the user's own number.
        near_today = abs((day - server_today()).days) <= 1
        target = target_for(session, current_user, day, create=near_today).target_kcal
    # Negative when the user ate more than the target
    remaining = None if target is None else round(target - totals.calories, 1)
    return DailySummary(
        eaten_on=day,
        totals=totals,
        meals=meals,
        daily_calorie_target=target,
        calories_remaining=remaining,
    )
