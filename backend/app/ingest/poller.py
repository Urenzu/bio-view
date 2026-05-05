import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.embeddings.openai import make_embedding_provider
from app.ingest.pipeline import run_ingest

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    log.info("monthly ingest poller firing")
    embedding = make_embedding_provider(settings.embedding_model_id)
    run_ingest(embedding)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    trigger = CronTrigger.from_crontab(settings.poll_cron, timezone="UTC")
    _scheduler.add_job(_job, trigger, id="ingest_monthly", replace_existing=True)
    _scheduler.start()
    log.info("scheduler started: cron=%s", settings.poll_cron)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
