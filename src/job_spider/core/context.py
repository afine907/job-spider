"""
爬虫上下文模块。

定义爬虫执行时的上下文环境，包含配置、HTTP客户端、日志器和指标收集器。
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
import uuid

import structlog


@runtime_checkable
class HttpClient(Protocol):
    """
    HTTP 客户端协议。

    定义爬虫使用的 HTTP 客户端接口，支持不同的实现（如 httpx、aiohttp）。
    """

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """
        发送 GET 请求。

        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
            timeout: 超时时间

        Returns:
            Any: 响应对象
        """
        ...

    async def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """
        发送 POST 请求。

        Args:
            url: 请求URL
            data: 表单数据
            json: JSON数据
            headers: 请求头
            timeout: 超时时间

        Returns:
            Any: 响应对象
        """
        ...

    async def close(self) -> None:
        """关闭客户端连接。"""
        ...


@runtime_checkable
class MetricsCollector(Protocol):
    """
    指标收集器协议。

    定义爬虫指标收集的接口，用于监控和统计。
    """

    def increment(self, name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """
        增加计数器。

        Args:
            name: 指标名称
            value: 增加的值
            tags: 标签
        """
        ...

    def timing(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """
        记录时间指标。

        Args:
            name: 指标名称
            value: 时间值（秒）
            tags: 标签
        """
        ...

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """
        设置仪表值。

        Args:
            name: 指标名称
            value: 当前值
            tags: 标签
        """
        ...


@dataclass
class SpiderContext:
    """
    爬虫上下文数据类。

    封装爬虫执行时需要的所有依赖和状态。

    Attributes:
        config: 配置对象
        http_client: HTTP 客户端
        logger: 日志器
        metrics: 指标收集器
        trace_id: 追踪ID
        metadata: 额外的元数据
        keyword: 搜索关键词
        location: 工作地点
        city: 城市
        page: 页码
        page_size: 每页数量
        limit: 爬取数量限制
        request_delay: 请求延迟范围
        timeout: 超时时间
        max_retries: 最大重试次数
        proxy: 代理地址

    Example:
        >>> from config.settings import get_settings
        >>> from config.logging import get_logger
        >>> settings = get_settings()
        >>> logger = get_logger(__name__)
        >>> ctx = SpiderContext(config=settings, logger=logger)
        >>> print(ctx.trace_id)  # 自动生成
    """

    config: Any  # Settings 类型，使用 Any 避免循环导入
    http_client: HttpClient | None = None
    logger: structlog.stdlib.BoundLogger = field(
        default_factory=lambda: structlog.get_logger()
    )
    metrics: MetricsCollector | None = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    # 爬虫运行参数
    keyword: str = ""          # 搜索关键词
    location: str = ""         # 工作地点
    city: str = ""             # 城市
    page: int = 1              # 页码
    page_size: int = 20        # 每页数量
    limit: int = 100           # 爬取数量限制
    request_delay: tuple[float, float] = (1.0, 3.0)  # 请求延迟范围
    timeout: float = 30.0      # 超时时间
    max_retries: int = 3       # 最大重试次数
    proxy: str | None = None   # 代理地址
    headers: dict[str, str] = field(default_factory=dict)  # 自定义请求头

    def get_delay(self) -> float:
        """
        获取随机延迟时间。

        Returns:
            float: 随机延迟秒数
        """
        import random
        return random.uniform(self.request_delay[0], self.request_delay[1])

    def with_trace_id(self, trace_id: str) -> "SpiderContext":
        """
        创建带有指定 trace_id 的新上下文。

        Args:
            trace_id: 追踪ID

        Returns:
            SpiderContext: 新的上下文实例

        Example:
            >>> ctx = SpiderContext(config=settings)
            >>> new_ctx = ctx.with_trace_id("custom-trace-123")
        """
        return SpiderContext(
            config=self.config,
            http_client=self.http_client,
            logger=self.logger,
            metrics=self.metrics,
            trace_id=trace_id,
            metadata=self.metadata.copy(),
            keyword=self.keyword,
            location=self.location,
            city=self.city,
            page=self.page,
            page_size=self.page_size,
            limit=self.limit,
            request_delay=self.request_delay,
            timeout=self.timeout,
            max_retries=self.max_retries,
            proxy=self.proxy,
            headers=self.headers.copy(),
        )

    def with_metadata(self, **kwargs: Any) -> "SpiderContext":
        """
        创建带有额外元数据的新上下文。

        Args:
            **kwargs: 元数据键值对

        Returns:
            SpiderContext: 新的上下文实例

        Example:
            >>> ctx = SpiderContext(config=settings)
            >>> new_ctx = ctx.with_metadata(source="boss", city="北京")
        """
        new_metadata = self.metadata.copy()
        new_metadata.update(kwargs)
        return SpiderContext(
            config=self.config,
            http_client=self.http_client,
            logger=self.logger,
            metrics=self.metrics,
            trace_id=self.trace_id,
            metadata=new_metadata,
            keyword=self.keyword,
            location=self.location,
            city=self.city,
            page=self.page,
            page_size=self.page_size,
            limit=self.limit,
            request_delay=self.request_delay,
            timeout=self.timeout,
            max_retries=self.max_retries,
            proxy=self.proxy,
            headers=self.headers.copy(),
        )
