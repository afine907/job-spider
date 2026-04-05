"""
配置模块。

提供应用程序配置和日志功能。

Example:
    >>> from config.settings import get_settings, Settings
    >>> from config.logging import get_logger, configure_logging
    >>>
    >>> settings = get_settings()
    >>> configure_logging(settings.log)
    >>> logger = get_logger(__name__)
"""

from config.settings import (
    Settings,
    DatabaseConfig,
    SpiderConfig,
    LogConfig,
    get_settings,
    reload_settings,
)
from config.logging import (
    get_logger,
    configure_logging,
    set_trace_id,
    get_trace_id,
    clear_trace_id,
)

__all__ = [
    # 配置类
    "Settings",
    "DatabaseConfig",
    "SpiderConfig",
    "LogConfig",
    # 配置函数
    "get_settings",
    "reload_settings",
    # 日志函数
    "get_logger",
    "configure_logging",
    "set_trace_id",
    "get_trace_id",
    "clear_trace_id",
]
