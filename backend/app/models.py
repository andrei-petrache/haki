from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class User(Base):
    """A registered user of the app."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    daily_calorie_target: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Food(Base):
    """A food in a user's personal list, with nutrients per 100 g."""

    __tablename__ = "foods"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_foods_user_id_name"),
        CheckConstraint(
            "calories_per_100g >= 0 AND protein_per_100g >= 0 "
            "AND carbs_per_100g >= 0 AND fat_per_100g >= 0",
            name="ck_foods_non_negative_nutrients",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    calories_per_100g: Mapped[float]
    protein_per_100g: Mapped[float]
    carbs_per_100g: Mapped[float]
    fat_per_100g: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MealEntry(Base):
    """An amount of a food eaten by a user on a given day and meal."""

    __tablename__ = "meal_entries"
    __table_args__ = (
        CheckConstraint("grams > 0", name="ck_meal_entries_positive_grams"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="ck_meal_entries_meal_type",
        ),
        Index("ix_meal_entries_user_id_eaten_on", "user_id", "eaten_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="RESTRICT"), index=True
    )
    eaten_on: Mapped[date]
    meal_type: Mapped[str] = mapped_column(String(20))
    grams: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    food: Mapped[Food] = relationship()