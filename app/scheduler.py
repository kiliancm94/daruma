from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def create_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()


def sync_jobs(
    scheduler: BackgroundScheduler,
    tasks: list,
    execute_fn,
) -> None:
    existing_job_ids = {job.id for job in scheduler.get_jobs()}
    desired_job_ids = set()

    for task in tasks:
        if not task.cron_expression or not task.enabled:
            continue
        desired_job_ids.add(task.id)

    # Remove jobs that should no longer exist
    for job_id in existing_job_ids:
        if job_id not in desired_job_ids:
            scheduler.remove_job(job_id)

    # Add jobs that don't exist yet
    for task in tasks:
        if task.id not in desired_job_ids:
            continue
        if task.id in existing_job_ids:
            continue
        parts = task.cron_expression.split()
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        scheduler.add_job(
            execute_fn,
            trigger=trigger,
            args=[task.id],
            id=task.id,
            name=task.name,
            replace_existing=True,
        )
