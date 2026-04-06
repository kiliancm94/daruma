"""CRUD operations for pipelines."""

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.pipeline import Pipeline, PipelineStep
from app.models.task import Task
from app.schemas.pipeline import PipelineUpdate
from app.utils.date_helpers import utcnow


def _validate_task_ids(session: Session, task_ids: list[str]) -> None:
    """Validate that all task IDs exist. Raises ValueError if not."""
    if not task_ids:
        raise ValueError("Pipeline requires at least one task")
    existing = {
        row[0] for row in session.query(Task.id).filter(Task.id.in_(task_ids)).all()
    }
    missing = set(task_ids) - existing
    if missing:
        raise ValueError(f"Invalid task IDs: {', '.join(sorted(missing))}")


def create(
    session: Session,
    name: str,
    description: str | None = None,
    task_ids: list[str] | None = None,
    enabled: bool = True,
) -> Pipeline:
    """Create a pipeline with ordered steps.

    Validates that all task_ids exist and at least one is provided.
    Raises ValueError for invalid task IDs or empty list.
    """
    if task_ids is None:
        task_ids = []
    _validate_task_ids(session, task_ids)
    pipeline = Pipeline(name=name, description=description, enabled=enabled)
    session.add(pipeline)
    session.flush()  # get pipeline.id before creating steps
    for order, task_id in enumerate(task_ids):
        step = PipelineStep(pipeline_id=pipeline.id, task_id=task_id, step_order=order)
        session.add(step)
    session.commit()
    session.refresh(pipeline)
    return pipeline


def get(session: Session, pipeline_id: str) -> Pipeline | None:
    return session.get(Pipeline, pipeline_id)


def get_by_name(session: Session, name: str) -> Pipeline | None:
    return session.query(Pipeline).filter(Pipeline.name == name).first()


def get_all(session: Session) -> list[Pipeline]:
    return session.query(Pipeline).order_by(Pipeline.created_at.desc()).all()


def update(session: Session, pipeline_id: str, **fields) -> Pipeline:
    """Update a pipeline. Raises NotFoundError if the pipeline does not exist."""
    if (pipeline := get(session, pipeline_id)) is None:
        raise NotFoundError(f"Pipeline not found: {pipeline_id}")
    validated = PipelineUpdate(**fields).model_dump(exclude_unset=True)
    if not validated:
        return pipeline
    for key, value in validated.items():
        setattr(pipeline, key, value)
    pipeline.updated_at = utcnow()
    session.commit()
    session.refresh(pipeline)
    return pipeline


def update_steps(session: Session, pipeline_id: str, task_ids: list[str]) -> Pipeline:
    """Replace all steps for a pipeline. Validates task IDs exist.

    Raises NotFoundError if pipeline not found.
    Raises ValueError for invalid task IDs.
    """
    if (pipeline := get(session, pipeline_id)) is None:
        raise NotFoundError(f"Pipeline not found: {pipeline_id}")
    _validate_task_ids(session, task_ids)
    # Delete existing steps
    for step in list(pipeline.steps):
        session.delete(step)
    session.flush()
    # Insert new ordered steps
    for order, task_id in enumerate(task_ids):
        step = PipelineStep(pipeline_id=pipeline.id, task_id=task_id, step_order=order)
        session.add(step)
    pipeline.updated_at = utcnow()
    session.commit()
    session.refresh(pipeline)
    return pipeline


def delete(session: Session, pipeline_id: str) -> None:
    """Delete a pipeline. Raises NotFoundError if the pipeline does not exist."""
    if (pipeline := get(session, pipeline_id)) is None:
        raise NotFoundError(f"Pipeline not found: {pipeline_id}")
    session.delete(pipeline)
    session.commit()
