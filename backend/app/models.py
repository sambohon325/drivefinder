import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Covers both consumer accounts and dealer accounts, split by role.

    Keeping one table avoids duplicating auth logic for two account types
    that otherwise behave identically (email + password, session cookie).
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="consumer")  # "consumer" | "dealer"

    # Dealer-only fields (null for consumers)
    dealer_name = Column(String, nullable=True)
    is_vicimus_client = Column(Boolean, default=False)
    trial_ends_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("ChatSession", back_populates="user")
    leads = relationship("Lead", back_populates="user")

    @property
    def is_trial_active(self) -> bool:
        if self.is_vicimus_client:
            return True
        if not self.trial_ends_at:
            return False
        return datetime.utcnow() < self.trial_ends_at

    @staticmethod
    def new_trial_window() -> datetime:
        return datetime.utcnow() + timedelta(days=30)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # null until signup gate
    location = Column(String, nullable=True)

    # Free-form state blob: current_make, current_model, current_body_style,
    # stock_color, milestones {body_style_preview_rendered, options_generated,
    # final_set_generated}, etc.
    state = Column(JSON, default=dict)

    is_ready_for_finance = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship(
        "ChatMessage", back_populates="session", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    vin = Column(String, nullable=True)
    vehicle_specs = Column(String, nullable=True)
    dealer_id = Column(String, nullable=True)
    dealer_name = Column(String, nullable=True)
    is_preferred_dealer = Column(Boolean, default=False)

    funding_strategy = Column(String, nullable=True)
    credit_tier = Column(String, nullable=True)
    logistics_intent = Column(String, nullable=True)
    dealer_cross_sell_allowed = Column(Boolean, default=False)

    status = Column(String, default="new")  # new | contacted | won | lost (placeholder)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="leads")


class NotifyRequest(Base):
    """Captured when someone asks for a make/model we don't carry. No
    notification pipeline is wired up to actually email these yet — this
    just gives the list a place to live until that's built."""
    __tablename__ = "notify_requests"

    id = Column(String, primary_key=True, default=gen_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    email = Column(String, nullable=False)
    requested_vehicle = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
