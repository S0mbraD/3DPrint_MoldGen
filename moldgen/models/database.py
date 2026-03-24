"""SQLite 数据库 — 项目数据、Agent 长期记忆"""

from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(12), primary_key=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    state = Column(String(50), default="created")
    model_path = Column(Text, nullable=True)
    mold_config = Column(Text, nullable=True)


class AgentMemoryRecord(Base):
    __tablename__ = "agent_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text, nullable=False)
    category = Column(String(50), default="preference")
    created_at = Column(DateTime, server_default=func.now())
    score = Column(Float, default=0.0)


def init_db(db_path: Path | str = "data/moldgen.db") -> sessionmaker:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
