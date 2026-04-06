"""
爬虫模块

导出所有爬虫类和相关数据模型。
"""

from .base import BaseSpider, CrawlResult, JobItem, SpiderContext, SpiderRegistry
from .zhilian import ZhilianSpider
from .zhilian_browser import ZhilianBrowserSpider
from .job51 import Job51Spider
from .mock import MockSpider, RemoteOKSpider

__all__ = [
    "BaseSpider",
    "CrawlResult",
    "JobItem",
    "SpiderContext",
    "SpiderRegistry",
    "ZhilianSpider",
    "ZhilianBrowserSpider",
    "Job51Spider",
    "MockSpider",
    "RemoteOKSpider",
]
