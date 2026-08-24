from datetime import date
from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    commander: Mapped[str] = mapped_column(String(160), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="player")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), nullable=True, unique=True)
    player: Mapped[Player | None] = relationship()

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    event_date: Mapped[date] = mapped_column(Date, default=date.today)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registrations: Mapped[list["Registration"]] = relationship(cascade="all, delete-orphan")
    rounds: Mapped[list["Round"]] = relationship(cascade="all, delete-orphan", order_by="Round.number")

class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "player_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    player: Mapped[Player] = relationship()

class Round(Base):
    __tablename__ = "rounds"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    number: Mapped[int]
    pods: Mapped[list["Pod"]] = relationship(cascade="all, delete-orphan", order_by="Pod.table_number")

class Pod(Base):
    __tablename__ = "pods"
    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"))
    table_number: Mapped[int]
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    draw: Mapped[bool] = mapped_column(Boolean, default=False)
    seats: Mapped[list["Seat"]] = relationship(cascade="all, delete-orphan", order_by="Seat.position")

class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[int] = mapped_column(primary_key=True)
    pod_id: Mapped[int] = mapped_column(ForeignKey("pods.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    position: Mapped[int]
    deck: Mapped[str] = mapped_column(String(160), default="")
    player: Mapped[Player] = relationship()
