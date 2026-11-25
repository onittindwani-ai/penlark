"""Penlark tables (prefix vp_). They sit on the shared Base."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sendora_core.db import Base, UTCDateTime, utcnow

DRAFT_STATUSES = ("draft", "pending_approval", "approved", "scheduled", "sending", "exported", "published", "rejected")
NOTE_KINDS = ("call", "comment", "email", "note", "fact")


class State(Base):
    __tablename__ = "vp_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Author(Base):
    __tablename__ = "vp_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    about: Mapped[str] = mapped_column(Text, default="")


class Sample(Base):
    __tablename__ = "vp_sample"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("vp_author.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), default="text")
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="pasted")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class VoiceProfile(Base):
    __tablename__ = "vp_voice_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("vp_author.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    stats: Mapped[dict] = mapped_column(JSON)
    guide: Mapped[str] = mapped_column(Text, default="")
    guide_source: Mapped[str] = mapped_column(String(40), default="offline stand in")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    diff: Mapped[list] = mapped_column(JSON, default=list)
    examples: Mapped[dict] = mapped_column(JSON, default=dict)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Note(Base):
    __tablename__ = "vp_note"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    who: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    occurred_on: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Idea(Base):
    __tablename__ = "vp_idea"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    note_ids: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    parts: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="inbox")  # inbox, approved, dropped
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Draft(Base):
    __tablename__ = "vp_draft"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("vp_author.id"), index=True)
    idea_id: Mapped[int | None] = mapped_column(ForeignKey("vp_idea.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="post")
    title: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_note_ids: Mapped[list] = mapped_column(JSON, default=list)
    claim_links: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), default="system")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Variant(Base):
    __tablename__ = "vp_variant"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("vp_draft.id"), index=True)
    label: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(300), default="")


class Schedule(Base):
    __tablename__ = "vp_schedule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("vp_draft.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30), default="linkedin")
    run_on: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned, exported, sent, failed
    adapter: Mapped[str] = mapped_column(String(30), default="file")
    external_id: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(String(300), default="")


class Performance(Base):
    __tablename__ = "vp_performance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_ref: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(30), default="unknown")
    posted_on: Mapped[str] = mapped_column(String(10), default="")
    text: Mapped[str] = mapped_column(Text)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Link(Base):
    __tablename__ = "vp_link"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    target: Mapped[str] = mapped_column(String(1000))
    post_ref: Mapped[str] = mapped_column(String(200), default="")
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(60), default="")
    medium: Mapped[str] = mapped_column(String(60), default="")
    campaign: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Click(Base):
    __tablename__ = "vp_click"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("vp_link.id"), index=True)
    visitor: Mapped[str] = mapped_column(String(64), default="")  # a hash, never an address
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Conversion(Base):
    __tablename__ = "vp_conversion"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int | None] = mapped_column(ForeignKey("vp_link.id"), nullable=True, index=True)
    lead_ref: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="lead")  # lead, customer
    value: Mapped[int] = mapped_column(Integer, default=0)  # cents
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Experiment(Base):
    __tablename__ = "vp_experiment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(60), default="link clicks")
    a_label: Mapped[str] = mapped_column(String(60), default="A")
    b_label: Mapped[str] = mapped_column(String(60), default="B")
    a_n: Mapped[int] = mapped_column(Integer, default=0)
    a_hits: Mapped[int] = mapped_column(Integer, default=0)
    b_n: Mapped[int] = mapped_column(Integer, default=0)
    b_hits: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")


class HouseRule(Base):
    __tablename__ = "vp_house_rule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # phrase, pattern
    value: Mapped[str] = mapped_column(String(300))
    note: Mapped[str] = mapped_column(String(300), default="")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
