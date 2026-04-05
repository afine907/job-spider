"""
核心模块。

提供爬虫框架的核心组件：上下文、注册中心和引擎。
"""

from job_spider.spiders.base import SpiderContext, SpiderRegistry
from job_spider.core.engine import SpiderEngine, SpiderResult
from job_spider.core.registry import register_spider

__all__ = [
    "SpiderContext",
    "SpiderEngine",
    "SpiderResult",
    "SpiderRegistry",
    "register_spider",
]
