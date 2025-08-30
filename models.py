from db import Base
from sqlalchemy.orm import mapped_column, Mapped
from typing import Optional
from sqlalchemy import Integer, String, Text

class Profile(Base):
    __tablename__ = "Profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    one_sentence_summary: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    detailed_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    slogan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

