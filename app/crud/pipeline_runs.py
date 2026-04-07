"""CRUD operations for pipeline runs."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.pipeline_run import PipelineRun
from app.schemas.pipeline import PipelineRunStatus, PipelineTrigger
from app.utils.date_helpers import utcnow


def create(
    session: Session,
    pipeline_id: str,
    trigger: PipelineTrigger = PipelineTrigger.manual,
) -> PipelineRun:
    """Create a pipeline run with status='running' and started_at=utcnow()."""
    run = PipelineRun(
        pipeline_id=pipeline_id,
        trigger=trigger,
        status=PipelineRunStatus.running,
        started_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get(session: Session, run_id: str) -> PipelineRun | None:
    return session.get(PipelineRun, run_id)


def update_step(session: Session, run_id: str, current_step: int) -> PipelineRun:
    """Update the current_step field. Raises NotFoundError if run not found."""
    if (run := get(session, run_id)) is None:
        raise NotFoundError(f"Pipeline run not found: {run_id}")
    run.current_step = current_step
    session.commit()
    session.refresh(run)
    return run


def complete(
    session: Session,
    run_id: str,
    status: PipelineRunStatus,
    finished_at: str | None = None,
    duration_ms: int | None = None,
) -> PipelineRun:
    """Mark a pipeline run as finished. Raises NotFoundError if run not found."""
    if (run := get(session, run_id)) is None:
        raise NotFoundError(f"Pipeline run not found: {run_id}")
    now = finished_at or utcnow()
    run.status = status
    run.finished_at = now
    if duration_ms is not None:
        run.duration_ms = duration_ms
    else:
        started = datetime.fromisoformat(run.started_at)
        finished = datetime.fromisoformat(now)
        run.duration_ms = int((finished - started).total_seconds() * 1000)
    session.commit()
    session.refresh(run)
    return run


def get_all(session: Session, pipeline_id: str | None = None) -> list[PipelineRun]:
    query = session.query(PipelineRun)
    if pipeline_id:
        query = query.filter(PipelineRun.pipeline_id == pipeline_id)
    return query.order_by(PipelineRun.started_at.desc()).all()


def get_last(session: Session, pipeline_id: str) -> PipelineRun | None:
    return (
        session.query(PipelineRun)
        .filter(PipelineRun.pipeline_id == pipeline_id)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
