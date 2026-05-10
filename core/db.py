from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    query = Column(Text, nullable=False)
    status = Column(String, default="pending")
    result = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

class Trace(Base):
    __tablename__ = "traces"
    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey("jobs.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    agent_id = Column(String)
    event_type = Column(String)
    payload = Column(JSON)

class EvalRun(Base):
    __tablename__ = "eval_runs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    test_case_id = Column(String)
    category = Column(String) # baseline, ambiguous, adversarial
    scores = Column(JSON) # Multi-dimensional scores
    total_score = Column(Float)
    justification = Column(Text)
    full_trace = Column(JSON)

class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id = Column(Integer, primary_key=True)
    agent_id = Column(String)
    version = Column(Integer)
    content = Column(Text)
    diff = Column(Text)
    justification = Column(Text)
    status = Column(String, default="pending") # pending, approved, rejected
    performance_delta = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./production_agent.db")
from sqlalchemy import create_engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
