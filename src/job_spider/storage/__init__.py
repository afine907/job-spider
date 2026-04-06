"""
存储层模块

提供数据库模型、数据仓库、数据导出和备份功能。
"""

from job_spider.storage.models import (
    JobRaw,
    JobProcessed,
    CrawlTask,
    JobCreate,
    JobResponse,
    SpiderConfig,
    SpiderResult,
)
from job_spider.storage.database import Database
from job_spider.storage.repository import JobRepository
from job_spider.storage.exporter import Exporter
from job_spider.storage.backup import (
    DatabaseBackup,
    BackupInfo,
    BackupResult,
    RestoreResult,
    BackupStatus,
)

__all__ = [
    # SQLAlchemy 模型
    "JobRaw",
    "JobProcessed",
    "CrawlTask",
    # Pydantic 模型
    "JobCreate",
    "JobResponse",
    "SpiderConfig",
    "SpiderResult",
    # 数据库和仓库
    "Database",
    "JobRepository",
    # 导出器
    "Exporter",
    # 备份模块
    "DatabaseBackup",
    "BackupInfo",
    "BackupResult",
    "RestoreResult",
    "BackupStatus",
]
