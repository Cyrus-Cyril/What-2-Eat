"""
app/db/orm_models.py
SQLAlchemy ORM 模型 —— 映射 MySQL 建表语句
"""
from datetime import datetime
from sqlalchemy import Integer, Float, String, Text, ForeignKey, BIGINT, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(BIGINT, ForeignKey("tag.id"))


class Restaurant(Base):
    __tablename__ = "restaurant"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class RestaurantTag(Base):
    __tablename__ = "restaurant_tag"

    restaurant_id: Mapped[str] = mapped_column(String(100), ForeignKey("restaurant.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("tag.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class UserTagPreference(Base):
    __tablename__ = "user_tag_preference"

    user_id: Mapped[str] = mapped_column(String(100), ForeignKey("app_user.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("tag.id"), primary_key=True)
    preference: Mapped[float] = mapped_column(Float, default=0.5)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class Interaction(Base):
    __tablename__ = "interaction"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), ForeignKey("app_user.id"), nullable=False)
    restaurant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class UserQuery(Base):
    __tablename__ = "user_query"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("app_user.id"))
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    radius: Mapped[int | None] = mapped_column(Integer)
    budget_min: Mapped[float | None] = mapped_column(Float)
    budget_max: Mapped[float | None] = mapped_column(Float)
    taste: Mapped[str | None] = mapped_column(String(100))
    query_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class Recommendation(Base):
    __tablename__ = "recommendation"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    query_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("user_query.id"))
    restaurant_id: Mapped[str | None] = mapped_column(String(100))
    restaurant_name: Mapped[str | None] = mapped_column(String(100))
    rank: Mapped[int | None] = mapped_column(Integer, name="rank_index")
    final_score: Mapped[float | None] = mapped_column(Float)
    score_distance: Mapped[float | None] = mapped_column(Float)
    score_price: Mapped[float | None] = mapped_column(Float)
    score_rating: Mapped[float | None] = mapped_column(Float)
    score_tag: Mapped[float | None] = mapped_column(Float)
    matched_tags: Mapped[list | dict | None] = mapped_column(JSON)
    reason_hint: Mapped[list | dict | None] = mapped_column(JSON)
    explain_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("app_user.id"))
    recommendation_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("recommendation.id"))
    restaurant_id: Mapped[str | None] = mapped_column(String(100))
    rating: Mapped[int | None] = mapped_column(Integer)
    chosen: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
