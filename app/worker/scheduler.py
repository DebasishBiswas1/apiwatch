"""
scheduler.py — APScheduler configuration and job registration.

APScheduler (Advanced Python Scheduler) runs jobs inside the current
process on a timer. It is the simplest possible scheduling solution —
no extra infrastructure, no broker, no worker process to manage.

Why APScheduler for Phase 1 and not Celery right away?
  Celery requires a broker (Redis), a separate worker process, task
  serialisation, and result backends. That is the right tool for
  production but adds four moving parts before we have proven the
  core polling logic works. APScheduler lets us build and verify the
  polling logic first, then swap the scheduler in Phase 2 without
  touching poller.py at all. The polling logic and the scheduling
  mechanism are intentionally separate files for exactly this reason.

What breaks with APScheduler at scale (Phase 2 will fix):
  1. Jobs run in the same process as the API — a slow poll blocks
     API event loop time.
  2. If the process restarts, in-flight jobs are lost.
  3. Cannot run multiple worker instances — jobs would be duplicated
     across processes.
  Celery + Redis solves all three. But none of these matter yet.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.worker.poller import poll_all_active_endpoints

logger = logging.getLogger(__name__)

# Module-level scheduler instance.
# Created once, started in lifespan startup, stopped in lifespan shutdown.
# AsyncIOScheduler runs jobs as coroutines on the existing asyncio event
# loop — the same loop FastAPI and SQLAlchemy are already using.
# This means no thread management and no event loop conflicts.
scheduler = AsyncIOScheduler()


def create_scheduler() -> AsyncIOScheduler:
    """
    Register all polling jobs and return the configured scheduler.

    Why a factory function instead of configuring at module level?
      Same reason as the FastAPI app factory — calling a function has
      no side effects at import time. Tests can call create_scheduler()
      to get a fresh configured instance without it auto-starting.

    IntervalTrigger(seconds=60):
      Fires poll_all_active_endpoints every 60 seconds.
      This is the global poll cycle — every active endpoint gets
      checked once per cycle. In Phase 2 we make this per-endpoint
      so different endpoints can have different intervals matching
      their configured interval_seconds field.

    max_instances=1:
      If a poll cycle takes longer than 60 seconds (many slow endpoints),
      APScheduler will not start a second overlapping cycle. It skips
      the tick instead. This prevents pile-up where cycles accumulate
      faster than they complete.

    id="poll_all_endpoints":
      A stable string ID for the job. Useful for inspecting, pausing,
      or removing the job programmatically later.
      e.g. scheduler.pause_job("poll_all_endpoints")
    """
    scheduler.add_job(
        poll_all_active_endpoints,
        trigger=IntervalTrigger(seconds=60),
        id="poll_all_endpoints",
        name="Poll all active endpoints",
        max_instances=1,
        replace_existing=True,
    )
    logger.info("Scheduler configured: poll_all_endpoints every 60 seconds")
    return scheduler


async def start_scheduler() -> None:
    """
    Start the scheduler. Called once at app startup in lifespan.

    scheduler.start() is non-blocking — it registers the jobs with
    the event loop and returns immediately. The jobs fire in the
    background while the app continues serving requests normally.
    """
    create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    """
    Gracefully shut down the scheduler. Called at app shutdown in lifespan.

    wait=False: do not wait for currently running jobs to finish.
    In production you would set wait=True to let in-flight polls
    complete before shutdown. For development, fast shutdown is
    more convenient.
    """
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")