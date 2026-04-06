"""
核心模块。

提供爬虫框架的核心组件：上下文、注册中心、引擎和优雅关闭。
"""

from job_spider.spiders.base import SpiderContext, SpiderRegistry
from job_spider.core.engine import SpiderEngine, SpiderResult
from job_spider.core.registry import register_spider
from job_spider.core.shutdown import (
    ShutdownManager,
    ShutdownState,
    ShutdownStats,
    shutdown_manager,
    get_shutdown_manager,
)

__all__ = [
    "SpiderContext",
    "SpiderEngine",
    "SpiderResult",
    "SpiderRegistry",
    "register_spider",
    "ShutdownManager",
    "ShutdownState",
    "ShutdownStats",
    "shutdown_manager",
    "get_shutdown_manager",
]
