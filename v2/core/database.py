"""
Database models and CRUD operations for MoceanAI V2.
Supports profiles (carried over from v1) and video history (new).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, String, Text, Integer, DateTime
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

from v2.core.config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Profile(Base):
    __tablename__ = "v2_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    one_sentence_summary: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    detailed_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_color: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    slogan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class VideoHistory(Base):
    __tablename__ = "v2_video_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    video_type: Mapped[str] = mapped_column(String(20), nullable=False)  # short_form / long_form
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    orientation: Mapped[str] = mapped_column(String(20), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    image_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    voice_actor: Mapped[str] = mapped_column(String(60), nullable=False)
    video_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


Session = sessionmaker(bind=engine, autocommit=False, expire_on_commit=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# CRUD  – Profiles
# ---------------------------------------------------------------------------
def create_profile(**kwargs) -> Profile:
    with Session() as s:
        profile = Profile(**kwargs)
        s.add(profile)
        s.commit()
        s.refresh(profile)
        return profile


def get_all_profiles() -> list[Profile]:
    with Session() as s:
        return list(s.query(Profile).all())


def get_profile(profile_id: int) -> Optional[Profile]:
    with Session() as s:
        return s.get(Profile, profile_id)


def update_profile(profile_id: int, **kwargs) -> Optional[Profile]:
    with Session() as s:
        profile = s.get(Profile, profile_id)
        if not profile:
            return None
        for k, v in kwargs.items():
            if v:
                setattr(profile, k, v)
        s.commit()
        s.refresh(profile)
        return profile


def delete_profile(profile_id: int) -> bool:
    with Session() as s:
        profile = s.get(Profile, profile_id)
        if not profile:
            return False
        s.delete(profile)
        s.commit()
        return True


# ---------------------------------------------------------------------------
# CRUD  – Video History
# ---------------------------------------------------------------------------
def save_video_record(**kwargs) -> VideoHistory:
    with Session() as s:
        record = VideoHistory(**kwargs)
        s.add(record)
        s.commit()
        s.refresh(record)
        return record


def get_all_videos() -> list[VideoHistory]:
    with Session() as s:
        return list(s.query(VideoHistory).order_by(VideoHistory.created_at.desc()).all())


def get_video(video_id: int) -> Optional[VideoHistory]:
    with Session() as s:
        return s.get(VideoHistory, video_id)


def delete_video_record(video_id: int) -> bool:
    with Session() as s:
        record = s.get(VideoHistory, video_id)
        if not record:
            return False
        s.delete(record)
        s.commit()
        return True
