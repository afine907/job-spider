"""
结构化日志模块。

使用 structlog 实现结构化日志，支持 JSON 和 Console 两种输出格式。
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.typing import EventDict, Processor

from config.settings import LogConfig, get_settings

# trace_id 上下文变量
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def set_trace_id(trace_id: str) -> None:
    """
    设置当前上下文的 trace_id。

    Args:
        trace_id: 追踪ID

    Example:
        >>> set_trace_id("abc123")
        >>> get_trace_id()
        'abc123'
    """
    trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    """
    获取当前上下文的 trace_id。

    Returns:
        str | None: 当前的 trace_id，未设置时返回 None
    """
    return trace_id_var.get()


def clear_trace_id() -> None:
    """清除当前上下文的 trace_id。"""
    trace_id_var.set(None)


def add_trace_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    structlog 处理器：添加 trace_id 到日志事件。

    Args:
        logger: 日志器实例
        method_name: 日志方法名
        event_dict: 日志事件字典

    Returns:
        EventDict: 处理后的日志事件字典
    """
    trace_id = get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def drop_color_message_key(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    structlog 处理器：移除颜色消息键（用于 JSON 输出）。

    Args:
        logger: 日志器实例
        method_name: 日志方法名
        event_dict: 日志事件字典

    Returns:
        EventDict: 处理后的日志事件字典
    """
    event_dict.pop("color_message", None)
    return event_dict


def get_processors(config: LogConfig) -> list[Processor]:
    """
    获取日志处理器链。

    Args:
        config: 日志配置

    Returns:
        list[Processor]: 处理器列表
    """
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # 添加 trace_id
    if config.include_trace:
        processors.append(add_trace_id)

    return processors


def configure_logging(config: LogConfig | None = None) -> None:
    """
    配置结构化日志系统。

    Args:
        config: 日志配置，为 None 时从全局配置获取

    Example:
        >>> configure_logging()  # 使用默认配置
        >>> configure_logging(LogConfig(level="DEBUG", format="json"))
    """
    if config is None:
        settings = get_settings()
        config = settings.log

    processors = get_processors(config)

    # 根据格式选择渲染器
    if config.format == "json":
        processors.append(drop_color_message_key)
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    processors.append(renderer)

    # 配置 structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准库 logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.level),
    )

    # 如果有输出文件，添加文件处理器
    if config.output_path:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            config.output_path,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, config.level))

        # 文件使用 JSON 格式
        file_processors = get_processors(config)
        file_processors.append(drop_color_message_key)
        file_processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))

        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=file_processors[:-1],
                processors=[file_processors[-1]],
            )
        )

        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    获取结构化日志器。

    Args:
        name: 日志器名称，通常使用 __name__

    Returns:
        structlog.stdlib.BoundLogger: 结构化日志器

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("应用启动", version="0.1.0")
    """
    return structlog.get_logger(name)


# 模块级别的便捷日志器
logger = get_logger(__name__)
