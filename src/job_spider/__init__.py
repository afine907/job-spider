"""
job-spider 职位爬虫框架。

一个灵活、可扩展的职位信息爬取框架，支持多种数据源和输出格式。

Example:
    >>> from job_spider import get_settings, get_logger, SpiderRegistry
    >>> settings = get_settings()
    >>> logger = get_logger(__name__)
    >>> spider_cls = SpiderRegistry.get("boss")
"""

__version__ = "0.1.0"
__author__ = "job-spider team"

# 导出公共 API
from job_spider.spiders.base import SpiderContext, SpiderRegistry
from job_spider.core.engine import SpiderEngine, SpiderResult
from job_spider.core.registry import register_spider

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    # 核心类
    "SpiderContext",
    "SpiderEngine",
    "SpiderResult",
    "SpiderRegistry",
    # 装饰器
    "register_spider",
]
