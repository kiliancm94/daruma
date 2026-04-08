"""Database engine and session management (SQLAlchemy)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base  # noqa: F401 — ensure models are importable
from app.models.task import Task  # noqa: F401 — register with Base.metadata
from app.models.run import Run  # noqa: F401
from app.models.skill import Skill  # noqa: F401
from app.models.task_skill import TaskSkill  # noqa: F401

_engine = None
_SessionLocal: sessionmaker | None = None


def _set_sqlite_pragmas(engine) -> None:
    """Enable WAL mode and foreign keys for every new SQLite connection."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _run_migrations(db_path: Path) -> None:
    """Run all pending Alembic migrations."""
    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")


def init_db(db_path: Path) -> None:
    """Create engine, apply pragmas, run migrations, configure session factory."""
    global _engine, _SessionLocal
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    _set_sqlite_pragmas(_engine)
    _run_migrations(db_path)
    _SessionLocal = sessionmaker(bind=_engine)


def get_db():
    """FastAPI dependency — yields a session, closes on cleanup."""
    session = _SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """Create a standalone session (CLI, background workers)."""
    return _SessionLocal()


def get_session_factory() -> sessionmaker:
    """Return the session factory (for background thread spawning)."""
    return _SessionLocal


def dispose() -> None:
    """Dispose engine (for clean test teardown)."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
