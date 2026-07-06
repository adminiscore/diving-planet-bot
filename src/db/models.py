"""
Database models for conversation tracking and analytics.

These models store conversation history, service selections,
and escalation events for the owner dashboard.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatwoot_conversation_id = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(200), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    language = Column(String(2), default="es")
    status = Column(String(20), default="active")  # active, resolved, escalated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Flow tracking
    current_step = Column(String(50), nullable=True)
    selected_service = Column(String(100), nullable=True)
    is_certified = Column(Boolean, nullable=True)
    location = Column(String(20), nullable=True)  # cartagena, island
    is_colombian = Column(Boolean, nullable=True)

    # Outcome
    booking_link_sent = Column(Boolean, default=False)
    escalated = Column(Boolean, default=False)
    escalation_reason = Column(Text, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    msg_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ServiceInquiry(Base):
    """Tracks which services customers ask about for analytics."""
    __tablename__ = "service_inquiries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), nullable=False, index=True)
    service_key = Column(String(100), nullable=False)
    led_to_booking = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
