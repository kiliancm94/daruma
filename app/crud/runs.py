"""CRUD operations for runs."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.database import Run


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRepo:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task_id: str, trigger: str) -> Run:
        run = Run(task_id=task_id, trigger=trigger, started_at=_utcnow())
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: str) -> Run | None:
        return self.session.get(Run, run_id)

    def update_output(self, run_id: str, stdout: str, activity: str = "") -> None:
        """Update partial stdout/activity while a run is still in progress."""
        run = self.get(run_id)
        if run:
            run.stdout = stdout
            run.activity = activity
            self.session.commit()

    def complete(
        self,
        run_id: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        activity: str = "",
    ) -> Run | None:
        run = self.get(run_id)
        if run is None:
            return None
        now = _utcnow()
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
        self.session.commit()
        self.session.refresh(run)
        return run

    def last_run(self, task_id: str) -> Run | None:
        return (
            self.session.query(Run)
            .filter(Run.task_id == task_id)
            .order_by(Run.started_at.desc())
            .first()
        )

    def list(self, task_id: str | None = None) -> list[Run]:
        query = self.session.query(Run)
        if task_id:
            query = query.filter(Run.task_id == task_id)
        return query.order_by(Run.started_at.desc()).all()
