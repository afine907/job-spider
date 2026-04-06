"""Task scheduler using APScheduler."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


class TaskStatus(Enum):
    """Task status enum."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """A scheduled task definition."""

    id: str
    name: str
    func: Callable
    trigger: str  # cron or interval
    trigger_args: dict[str, Any]
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskScheduler:
    """Task scheduler for spider jobs."""

    def __init__(self):
        """Initialize task scheduler."""
        self._scheduler = AsyncIOScheduler()
        self._tasks: dict[str, ScheduledTask] = {}

    def add_task(
        self,
        task_id: str,
        func: Callable,
        trigger: str = "interval",
        **trigger_args: Any,
    ) -> ScheduledTask:
        """Add a scheduled task.

        Args:
            task_id: Unique task identifier
            func: Async function to execute
            trigger: Trigger type ('cron' or 'interval')
            **trigger_args: Trigger arguments

        Returns:
            ScheduledTask instance
        """
        task = ScheduledTask(
            id=task_id,
            name=task_id,
            func=func,
            trigger=trigger,
            trigger_args=trigger_args,
        )

        # Create trigger
        if trigger == "cron":
            trigger_obj = CronTrigger(**trigger_args)
        else:
            trigger_obj = IntervalTrigger(**trigger_args)

        # Add job to scheduler
        self._scheduler.add_job(
            func,
            trigger=trigger_obj,
            id=task_id,
            name=task_id,
        )

        self._tasks[task_id] = task
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was removed
        """
        if task_id in self._tasks:
            self._scheduler.remove_job(task_id)
            del self._tasks[task_id]
            return True
        return False

    def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was paused
        """
        if task_id in self._tasks:
            self._scheduler.pause_job(task_id)
            self._tasks[task_id].enabled = False
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was resumed
        """
        if task_id in self._tasks:
            self._scheduler.resume_job(task_id)
            self._tasks[task_id].enabled = True
            return True
        return False

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID.

        Args:
            task_id: Task identifier

        Returns:
            ScheduledTask or None
        """
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[ScheduledTask]:
        """List all scheduled tasks.

        Returns:
            List of ScheduledTask
        """
        return list(self._tasks.values())

    async def run_task_now(self, task_id: str) -> bool:
        """Run a task immediately.

        Args:
            task_id: Task identifier

        Returns:
            True if task was triggered
        """
        task = self._tasks.get(task_id)
        if task:
            await task.func()
            return True
        return False

    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler.

        Args:
            wait: Wait for running jobs to complete
        """
        self._scheduler.shutdown(wait=wait)

    def __enter__(self) -> "TaskScheduler":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()


# Convenience functions for common schedules
def daily(func: Callable, hour: int = 0, minute: int = 0) -> ScheduledTask:
    """Schedule a function to run daily.

    Args:
        func: Function to schedule
        hour: Hour to run (0-23)
        minute: Minute to run (0-59)

    Returns:
        ScheduledTask
    """
    scheduler = TaskScheduler()
    return scheduler.add_task(
        task_id=func.__name__,
        func=func,
        trigger="cron",
        hour=hour,
        minute=minute,
    )


def hourly(func: Callable) -> ScheduledTask:
    """Schedule a function to run hourly.

    Args:
        func: Function to schedule

    Returns:
        ScheduledTask
    """
    scheduler = TaskScheduler()
    return scheduler.add_task(
        task_id=func.__name__,
        func=func,
        trigger="interval",
        hours=1,
    )


async def scheduled_backup_task() -> None:
    """
    定时备份任务函数。

    根据配置创建数据库备份并清理旧备份。
    """
    from pathlib import Path
    from config.settings import get_settings
    from job_spider.storage.backup import DatabaseBackup
    from config.logging import get_logger

    logger = get_logger("scheduler")
    settings = get_settings()

    db_path = Path(settings.database.sqlite_path)
    if not db_path.exists():
        logger.warning("scheduled_backup_skipped", reason="database_not_found")
        return

    backup_manager = DatabaseBackup(
        db_path=db_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    # 创建备份
    result = backup_manager.create_backup()
    if result.success:
        logger.info(
            "scheduled_backup_created",
            name=result.backup_name,
            size=result.size,
        )

        # 清理旧备份
        deleted = backup_manager.cleanup_old_backups()
        if deleted:
            logger.info("scheduled_backup_cleaned", deleted_count=len(deleted))
    else:
        logger.error("scheduled_backup_failed", message=result.message)


def setup_scheduled_backup(scheduler: TaskScheduler, interval_hours: int | None = None) -> ScheduledTask | None:
    """
    设置定时备份任务。

    Args:
        scheduler: 任务调度器实例
        interval_hours: 备份间隔（小时），默认从配置读取

    Returns:
        ScheduledTask 或 None（如果未启用）
    """
    from config.settings import get_settings
    from config.logging import get_logger

    logger = get_logger("scheduler")
    settings = get_settings()

    # 检查是否启用定时备份
    if not settings.backup.enable_scheduled_backup:
        logger.info("scheduled_backup_disabled")
        return None

    if interval_hours is None:
        interval_hours = settings.backup.backup_interval_hours

    task = scheduler.add_task(
        task_id="scheduled_backup",
        func=scheduled_backup_task,
        trigger="interval",
        hours=interval_hours,
    )

    logger.info("scheduled_backup_enabled", interval_hours=interval_hours)
    return task
