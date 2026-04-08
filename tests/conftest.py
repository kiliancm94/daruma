from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.task import Task  # noqa: F401 — register with Base.metadata
from app.models.run import Run  # noqa: F401
from app.models.skill import Skill  # noqa: F401
from app.models.task_skill import TaskSkill  # noqa: F401
from app.models.pipeline import Pipeline, PipelineStep  # noqa: F401
from app.models.pipeline_run import PipelineRun  # noqa: F401


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def engine(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)
