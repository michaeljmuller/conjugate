"""SQLAlchemy ORM models.

Normalized so the planned add-ons attach with no restructuring: example
sentences and pronunciation audio hang off a single ``Form`` row (columns already
present, left null for now).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Verb(Base):
    __tablename__ = "verbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    infinitive: Mapped[str] = mapped_column(String(64), unique=True, index=True)
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
    form_text: Mapped[str] = mapped_column(String(64))
    # Example sentence illustrating this form, in English and its pt-PT translation.
    example_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_pt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # --- Future add-on attaches here (null for now) ---
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    verb: Mapped[Verb] = relationship(back_populates="forms")


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
