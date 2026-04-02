"""CRUD operations for runs."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.run import Run
from app.utils.date_helpers import utcnow


def create(session: Session, task_id: str, trigger: str) -> Run:
    run = Run(task_id=task_id, trigger=trigger)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get(session: Session, run_id: str) -> Run | None:
    return session.get(Run, run_id)


def update_output(
    session: Session, run_id: str, stdout: str, activity: str = ""
) -> None:
    """Update partial stdout/activity while a run is still in progress."""
    run = get(session, run_id)
    if run:
        run.stdout = stdout
        run.activity = activity
        session.commit()


def complete(
    session: Session,
    run_id: str,
    status: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    activity: str = "",
) -> Run:
    """Mark a run as complete. Raises NotFoundError if the run does not exist."""
    run = get(session, run_id)
    if run is None:
        raise NotFoundError(f"Run not found: {run_id}")
    now = utcnow()
    started = datetime.fromisoformat(run.started_at)
    finished = datetime.fromisoformat(now)
    duration_ms = int((finished - started).total_seconds() * 1000)
    run.status = status
    run.finished_at = now
    run.duration_ms = duration_ms
    run.stdout = stdout
    run.stderr = stderr
    run.exit_code = exit_code
    run.activity = activity
    session.commit()
    session.refresh(run)
    return run


def get_last(session: Session, task_id: str) -> Run | None:
    return (
        session.query(Run)
        .filter(Run.task_id == task_id)
        .order_by(Run.started_at.desc())
        .first()
    )


def get_all(session: Session, task_id: str | None = None) -> list[Run]:
    query = session.query(Run)
    if task_id:
        query = query.filter(Run.task_id == task_id)
    return query.order_by(Run.started_at.desc()).all()
