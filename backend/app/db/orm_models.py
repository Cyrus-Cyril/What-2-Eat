"""
app/db/orm_models.py
SQLAlchemy ORM 模型 —— 映射 schema.sql 中的所有表
"""
from datetime import datetime
from sqlalchemy import Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tag.id"))


class Restaurant(Base):
    __tablename__ = "restaurant"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[str | None] = mapped_column(Text)


class RestaurantTag(Base):
    __tablename__ = "restaurant_tag"

    restaurant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tag.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[str | None] = mapped_column(Text)


class UserTagPreference(Base):
    __tablename__ = "user_tag_preference"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tag.id"), primary_key=True)
    preference: Mapped[float] = mapped_column(Float, default=0.5)
    updated_at: Mapped[str | None] = mapped_column(Text)


class Interaction(Base):
    __tablename__ = "interaction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    restaurant_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[str | None] = mapped_column(Text)


class UserQuery(Base):
    __tablename__ = "user_query"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text)
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    radius: Mapped[int | None] = mapped_column(Integer)
    budget_min: Mapped[float | None] = mapped_column(Float)
    budget_max: Mapped[float | None] = mapped_column(Float)
    taste: Mapped[str | None] = mapped_column(Text)
    query_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class Recommendation(Base):
    __tablename__ = "recommendation"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    query_id: Mapped[str | None] = mapped_column(Text, ForeignKey("user_query.id"))
    restaurant_id: Mapped[str | None] = mapped_column(Text)
    restaurant_name: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int | None] = mapped_column(Integer)
    final_score: Mapped[float | None] = mapped_column(Float)
    score_distance: Mapped[float | None] = mapped_column(Float)
    score_price: Mapped[float | None] = mapped_column(Float)
    score_rating: Mapped[float | None] = mapped_column(Float)
    score_tag: Mapped[float | None] = mapped_column(Float)
    matched_tags: Mapped[str | None] = mapped_column(Text)
    reason_hint: Mapped[str | None] = mapped_column(Text)
    explain_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text)
    recommendation_id: Mapped[str | None] = mapped_column(Text, ForeignKey("recommendation.id"))
    restaurant_id: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
    chosen: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(Text)
