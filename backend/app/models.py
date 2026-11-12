from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")

# A list of strings: JSONB in PostgreSQL, which a GIN index can search with
# @> ("contains"); plain JSON elsewhere (the tests' SQLite)
StringList = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class User(Base):
    """A registered user of the app."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # When the password was last changed; null if never. Every token carries
    # it (app.security.password_stamp), so a change refuses older tokens.
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    daily_calorie_target: Mapped[int | None] = mapped_column(default=None)
    # "en" or "ro"; null follows the browser's language
    language: Mapped[str | None] = mapped_column(String(5), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CatalogSource(Base):
    """Where catalog rows come from, under which licence, credited how.

    Shared by everyone and written only by the catalog import, never by a
    request: catalog tables hold no user data and no user_id.
    """

    __tablename__ = "catalog_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable name the import finds its source by, e.g. "usda-fdc-sr-legacy"
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    # SPDX identifier, e.g. "CC0-1.0", "Unlicense", "ODbL-1.0"
    license: Mapped[str] = mapped_column(String(50))
    # The credit line shown to users, in the source's requested form
    attribution: Mapped[str] = mapped_column(String(1000))
    # Whether the licence requires that credit on screen (ODbL, CC-BY-SA),
    # rather than it being a courtesy (CC0, Unlicense)
    attribution_required: Mapped[bool]
    # Whether a database derived from it must keep the same licence
    share_alike: Mapped[bool]
    # The dataset's own version: a release date or a commit SHA
    version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogFood(Base):
    """A food of the shared catalog, with nutrients per 100 g."""

    __tablename__ = "catalog_foods"
    __table_args__ = (
        # What makes the import idempotent: one row per item of a source
        UniqueConstraint(
            "source_id", "source_ref", name="uq_catalog_foods_source_id_source_ref"
        ),
        CheckConstraint(
            "calories_per_100g >= 0 AND protein_per_100g >= 0 "
            "AND carbs_per_100g >= 0 AND fat_per_100g >= 0",
            name="ck_catalog_foods_non_negative_nutrients",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_sources.id"))
    # The item's id at its source, e.g. a USDA FDC id
    source_ref: Mapped[str] = mapped_column(String(100))
    # English, the app's first language; name_ro when the data has one
    name: Mapped[str] = mapped_column(String(100))
    name_ro: Mapped[str | None] = mapped_column(String(100), default=None)
    # Both names, lower case, without diacritics (app.catalog_search)
    search_text: Mapped[str] = mapped_column(String(250))
    calories_per_100g: Mapped[float]
    protein_per_100g: Mapped[float]
    carbs_per_100g: Mapped[float]
    fat_per_100g: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[CatalogSource] = relationship()


class CatalogExercise(Base):
    """An exercise of the shared catalog."""

    __tablename__ = "catalog_exercises"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_ref",
            name="uq_catalog_exercises_source_id_source_ref",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_sources.id"))
    source_ref: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    name_ro: Mapped[str | None] = mapped_column(String(100), default=None)
    search_text: Mapped[str] = mapped_column(String(250))
    # The source's own vocabulary, in English, e.g. "strength", "barbell";
    # the frontend translates it
    category: Mapped[str | None] = mapped_column(String(30), default=None)
    equipment: Mapped[str | None] = mapped_column(String(30), default=None)
    level: Mapped[str | None] = mapped_column(String(30), default=None)
    force: Mapped[str | None] = mapped_column(String(30), default=None)
    mechanic: Mapped[str | None] = mapped_column(String(30), default=None)
    primary_muscles: Mapped[list[str]] = mapped_column(StringList)
    secondary_muscles: Mapped[list[str]] = mapped_column(StringList)
    # Paths of the images inside the source, kept as a reference only: they
    # are not served until their origin and hosting are decided
    image_refs: Mapped[list[str]] = mapped_column(StringList)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[CatalogSource] = relationship()


# Search reads search_text with LIKE '%word%', which a B-tree cannot serve.
# A trigram GIN index (pg_trgm) can, for words of 3 letters or more; the
# extension is created by the migration. PostgreSQL only: elsewhere these
# are plain indexes.
Index(
    "ix_catalog_foods_search_text_trgm",
    CatalogFood.search_text,
    postgresql_using="gin",
    postgresql_ops={"search_text": "gin_trgm_ops"},
)
Index(
    "ix_catalog_exercises_search_text_trgm",
    CatalogExercise.search_text,
    postgresql_using="gin",
    postgresql_ops={"search_text": "gin_trgm_ops"},
)
# Filtering by muscle: primary_muscles @> '["chest"]'. jsonb_path_ops is
# smaller than the default and serves exactly @>.
Index(
    "ix_catalog_exercises_primary_muscles",
    CatalogExercise.primary_muscles,
    postgresql_using="gin",
    postgresql_ops={"primary_muscles": "jsonb_path_ops"},
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
        # One copy of a catalog food per user. NULLs never conflict, so
        # foods typed in by hand are not limited.
        UniqueConstraint(
            "user_id", "catalog_food_id", name="uq_foods_user_id_catalog_food_id"
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
    # The catalog food this one was copied from, if any. A copy, not a
    # reference: a later import never changes what the user logged, and
    # the user may edit it. Nullable, so the previous version of the app,
    # which does not know the column, still inserts foods.
    catalog_food_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_foods.id", name="fk_foods_catalog_food_id"), default=None
    )
    # When the user marked it as a favourite; null when it is not one.
    # Nullable without a default, so the previous version still inserts;
    # a time rather than a nullable flag, which would have three states.
    favourited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Read-only: for the catalog's names next to the user's own one
    catalog_food: Mapped[CatalogFood | None] = relationship()

    @property
    def favourite(self) -> bool:
        """Whether the user marked this food as a favourite."""
        return self.favourited_at is not None


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


class QuickEntry(Base):
    """A one-off amount of calories (and maybe macros) logged without a food.

    A table of its own, not a meal_entries row with a null food_id: the
    previous version reads entry.food on every meal entry, so after a
    rollback a null food would turn a whole day into a 500. This table it
    simply never reads.
    """

    __tablename__ = "quick_entries"
    __table_args__ = (
        CheckConstraint(
            "calories >= 0 AND protein >= 0 AND carbs >= 0 AND fat >= 0",
            name="ck_quick_entries_non_negative_nutrients",
        ),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="ck_quick_entries_meal_type",
        ),
        Index("ix_quick_entries_user_id_eaten_on", "user_id", "eaten_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    eaten_on: Mapped[date]
    meal_type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    # The amounts themselves, not per 100 g: there is no food to scale
    calories: Mapped[float]
    protein: Mapped[float]
    carbs: Mapped[float]
    fat: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Exercise(Base):
    """An exercise in a user's personal catalog, e.g. "Bench press"."""

    __tablename__ = "exercises"
    __table_args__ = (
        # One copy of a catalog exercise per user, as for foods
        UniqueConstraint(
            "user_id",
            "catalog_exercise_id",
            name="uq_exercises_user_id_catalog_exercise_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The catalog exercise this one was copied from, if any (see
    # Food.catalog_food_id)
    catalog_exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_exercises.id", name="fk_exercises_catalog_exercise_id"),
        default=None,
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
    # The program day it was started from, so the editor can show the plan
    # next to what was done; null for a workout logged by hand. SET NULL:
    # deleting or replacing the day leaves the workout whole, only unlinked.
    # Nullable, so the previous version, which does not know it, still inserts.
    program_day_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "program_days.id",
            ondelete="SET NULL",
            name="fk_workouts_program_day_id",
        ),
        default=None,
        index=True,
    )
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


class Program(Base):
    """A user's weekly training plan, e.g. "Push/Pull/Legs"."""

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Deleting the program leaves its days to ON DELETE CASCADE (passive_deletes)
    days: Mapped[list[ProgramDay]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProgramDay.position",
    )


# Unique per user whatever the case, as exercise names are. Its leading
# user_id column also serves lookups by user.
Index(
    "uq_programs_user_id_lower_name",
    Program.user_id,
    func.lower(Program.name),
    unique=True,
)


class ProgramDay(Base):
    """One training day of a program, e.g. day 1, "Push"."""

    __tablename__ = "program_days"
    __table_args__ = (
        # Its leading program_id column also serves lookups by program
        UniqueConstraint(
            "program_id", "position", name="uq_program_days_program_id_position"
        ),
        CheckConstraint("position BETWEEN 1 AND 7", name="ck_program_days_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE")
    )
    # The day's place in the week, 1 to 7
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(100))

    program: Mapped[Program] = relationship(back_populates="days")
    # In the order they were added, as in a workout
    exercises: Mapped[list[ProgramExercise]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProgramExercise.id",
    )


class ProgramExercise(Base):
    """One planned exercise of a program day: sets of reps at a weight."""

    __tablename__ = "program_exercises"
    __table_args__ = (
        CheckConstraint("sets > 0", name="ck_program_exercises_positive_sets"),
        CheckConstraint("reps > 0", name="ck_program_exercises_positive_reps"),
        CheckConstraint(
            "weight_kg >= 0", name="ck_program_exercises_non_negative_weight"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_day_id: Mapped[int] = mapped_column(
        ForeignKey("program_days.id", ondelete="CASCADE"), index=True
    )
    # Deferred, as WorkoutExercise.exercise_id is, and for the same reason,
    # one level further down: deleting a user reaches these rows only through
    # programs and program_days. NO ACTION, not RESTRICT: PostgreSQL never
    # defers RESTRICT. Deleting an exercise still in a plan fails at commit,
    # in this version and in the previous one alike: a 409, nothing deleted.
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", deferrable=True, initially="DEFERRED"),
        index=True,
    )
    sets: Mapped[int]
    reps: Mapped[int]
    # 0 for bodyweight exercises
    weight_kg: Mapped[float]

    day: Mapped[ProgramDay] = relationship(back_populates="exercises")
    # One-way on purpose, as WorkoutExercise.exercise
    exercise: Mapped[Exercise] = relationship()
