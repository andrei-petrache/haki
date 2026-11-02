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


class Exercise(Base):
    """An exercise in a user's personal catalog, e.g. "Bench press"."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Unique per user whatever the case: "Squat" and "squat" are one exercise.
# Its leading user_id column also serves lookups by user.
Index(
    "uq_exercises_user_id_lower_name",
    Exercise.user_id,
    func.lower(Exercise.name),
    unique=True,
)


class Workout(Base):
    """A training session of a user on a given day."""

    __tablename__ = "workouts"
    __table_args__ = (
        Index("ix_workouts_user_id_performed_on", "user_id", "performed_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    performed_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # In the order they were added. Replacing the list deletes the old rows
    # (delete-orphan); deleting the workout leaves that to the database's
    # ON DELETE CASCADE (passive_deletes) instead of loading every row first.
    exercises: Mapped[list[WorkoutExercise]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutExercise.id",
    )


class WorkoutExercise(Base):
    """One exercise as done in one workout; its sets hang off this row."""

    __tablename__ = "workout_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("workouts.id", ondelete="CASCADE"), index=True
    )
    # Deferred: checked at COMMIT, not after each statement. Deleting a user
    # cascades to their exercises directly, but to these rows only two levels
    # down, through workouts; PostgreSQL checks the exercises' cascade before
    # it reaches them, so an immediate check (RESTRICT or NO ACTION alike)
    # would make deleting a user fail. Deleting a used exercise still fails,
    # at commit, which commit_or_conflict turns into a 409.
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )

    workout: Mapped[Workout] = relationship(back_populates="exercises")
    # One-way on purpose: with a list on Exercise, the ORM would try to null
    # exercise_id here when an exercise is deleted, instead of letting the
    # database refuse
    exercise: Mapped[Exercise] = relationship()
    sets: Mapped[list[WorkoutSet]] = relationship(
        back_populates="workout_exercise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkoutSet.id",
    )


class WorkoutSet(Base):
    """One set of an exercise in a workout: repetitions at a weight."""

    __tablename__ = "workout_sets"
    __table_args__ = (
        CheckConstraint("reps > 0", name="ck_workout_sets_positive_reps"),
        CheckConstraint("weight_kg >= 0", name="ck_workout_sets_non_negative_weight"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("workout_exercises.id", ondelete="CASCADE"), index=True
    )
    reps: Mapped[int]
    # 0 for bodyweight exercises
    weight_kg: Mapped[float]

    workout_exercise: Mapped[WorkoutExercise] = relationship(back_populates="sets")
