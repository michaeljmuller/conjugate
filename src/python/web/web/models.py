"""SQLAlchemy ORM models.

Normalized so the planned add-ons attach with no restructuring: example
sentences and pronunciation audio hang off a single ``Form`` row (columns already
present, left null for now).
"""

from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .languages import DEFAULT_LANGUAGE


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSettings(Base):
    """Per-user preferences as one JSON blob, so new settings add keys, not
    columns (and thus need no migration under the create_all-only schema).

    Current keys:

    ``language``
        Which language is being drilled, e.g. ``"pt-PT"``. Absent ⇒ the default.
    ``tenses``
        ``{<language>: [{"key": <tense_key>, "enabled": bool}, …]}`` in display
        order, per language — the catalogues differ, so one flat list cannot
        serve both. A bare list (the pre-Italian shape) is read as the default
        language's. Absent ⇒ all tenses enabled in canonical order.
    ``interface``
        ``labels`` (English vs native tense names) and ``show_accents``.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Verb(Base):
    __tablename__ = "verbs"
    # Infinitives are unique per language, not globally: Portuguese and Italian
    # never collide in practice, but nothing guarantees that and the drill has
    # to be able to tell a pt "partir" from an it one.
    __table_args__ = (
        UniqueConstraint("language", "infinitive", name="uq_verb_language_infinitive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The adapter that produced this verb, e.g. "pt-PT". server_default fills
    # existing rows when the column is added to a database that predates it.
    language: Mapped[str] = mapped_column(
        String(8), index=True, default=DEFAULT_LANGUAGE, server_default=DEFAULT_LANGUAGE
    )
    infinitive: Mapped[str] = mapped_column(String(64), index=True)
    past_participle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    present_participle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Filled in later (English gloss); nullable so seeding stays simple.
    translation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    forms: Mapped[list["Form"]] = relationship(
        back_populates="verb", cascade="all, delete-orphan"
    )


class Form(Base):
    __tablename__ = "forms"
    __table_args__ = (
        UniqueConstraint("verb_id", "tense", "person", name="uq_form_verb_tense_person"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    verb_id: Mapped[int] = mapped_column(ForeignKey("verbs.id"), index=True)
    tense: Mapped[str] = mapped_column(String(40))
    person: Mapped[str] = mapped_column(String(8))
    # The form shown as the answer. Other equally valid forms hang off
    # ``variants``; both grade as correct.
    form_text: Mapped[str] = mapped_column(String(64))
    # Example sentence illustrating this form, in English and its pt-PT translation.
    example_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_pt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # --- Future add-on attaches here (null for now) ---
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    verb: Mapped[Verb] = relationship(back_populates="forms")
    variants: Mapped[list["FormVariant"]] = relationship(
        back_populates="form", cascade="all, delete-orphan"
    )

    @property
    def accepted(self) -> list[str]:
        """Every form that counts as a correct answer, display form first."""
        return [self.form_text, *(v.text for v in self.variants)]


class FormVariant(Base):
    """An alternative form that is just as correct as ``Form.form_text``.

    Portuguese genuinely offers more than one form in some cells — ``oiço`` and
    ``ouço`` are both current, and the past participle can have a regular and a
    short version. The drill shows one and accepts them all.

    A separate table rather than a column on ``forms`` because the schema is
    created by ``create_all()`` alone: it adds missing *tables* to an existing
    database but will not add a column, so a new table needs no migration.
    """

    __tablename__ = "form_variants"
    __table_args__ = (
        UniqueConstraint("form_id", "text", name="uq_form_variant_form_text"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("forms.id"), index=True)
    text: Mapped[str] = mapped_column(String(64))

    form: Mapped[Form] = relationship(back_populates="variants")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("forms.id"), index=True)
    submitted_text: Mapped[str] = mapped_column(String(128))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    # correct | accent | typo | wrong — lets later stats separate real errors
    # (wrong) from slips (accent/typo) when ranking hardest conjugations.
    verdict: Mapped[str] = mapped_column(String(8), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
