"""
存储层模块

提供数据库模型、数据仓库和数据导出功能。
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
]
