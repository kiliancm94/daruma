from types import SimpleNamespace
from unittest.mock import MagicMock
from app.scheduler import sync_jobs


def _make_task(**kwargs):
    """Create a task-like object with attribute access."""
    defaults = {
        "id": "abc",
        "name": "T",
        "prompt": "p",
        "cron_expression": None,
        "allowed_tools": None,
        "enabled": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_sync_adds_enabled_cron_tasks():
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []
    tasks = [_make_task(cron_expression="0 8 * * *")]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_called_once()
    call_kwargs = scheduler.add_job.call_args
    assert call_kwargs.kwargs["id"] == "abc"


def test_sync_removes_disabled_tasks():
    job = MagicMock()
    job.id = "abc"
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [job]
    tasks = [_make_task(cron_expression="0 8 * * *", enabled=False)]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.remove_job.assert_called_once_with("abc")


def test_sync_removes_jobs_for_deleted_tasks():
    job = MagicMock()
    job.id = "deleted-task"
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [job]
    sync_jobs(scheduler, tasks=[], execute_fn=MagicMock())
    scheduler.remove_job.assert_called_once_with("deleted-task")


def test_sync_skips_tasks_without_cron():
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []
    tasks = [_make_task()]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_not_called()
