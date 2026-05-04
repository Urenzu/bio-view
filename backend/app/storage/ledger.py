from contextlib import contextmanager
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Integer, String, DateTime, JSON, Text, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, default="")
    picture = Column(String, default="")
    google_sub = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Paper(Base):
    __tablename__ = "papers"
    id = Column(Integer, primary_key=True)
    doi = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    source = Column(String, nullable=False, index=True)
    meca_key = Column(String, nullable=False, unique=True)
    title = Column(Text)
    subject = Column(String, index=True)
    authors = Column(JSON)
    posted_date = Column(String, index=True)
    jats_path = Column(String)
    embedded_in = Column(JSON, default=list)
    status = Column(String, default="pending", index=True)
    error = Column(Text)
    bytes_downloaded = Column(Integer, default=0)
    ingested_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("doi", "version", name="uq_paper_doi_version"),)


class MecaState(Base):
    __tablename__ = "meca_states"
    id = Column(Integer, primary_key=True)
    meca_key = Column(String, nullable=False, unique=True, index=True)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)  # done | skipped | failed
    skip_reason = Column(String)
    attempt_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime)
    last_error = Column(Text)
    paper_id = Column(Integer)


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    bytes_downloaded = Column(Integer, default=0)
    papers_added = Column(Integer, default=0)
    papers_failed = Column(Integer, default=0)
    notes = Column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)  # null = anonymous
    created_at = Column(DateTime, default=datetime.utcnow)
    title = Column(String)
    pinned = Column(Boolean, default=False)
    pinned_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    gen_model_id = Column(String)
    embedding_model_id = Column(String)
    reranker_model_id = Column(String)
    retrieved_doi_versions = Column(JSON)
    hits_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=not _is_sqlite,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
