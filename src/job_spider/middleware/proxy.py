"""
代理池中间件

管理代理服务器列表，支持健康检查、优先级排序和失效代理移除。
"""

import asyncio
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Literal, Optional, Protocol
from urllib.parse import urlparse


class ProxyProtocol(IntEnum):
    """代理协议类型"""
    HTTP = 1
    HTTPS = 2
    SOCKS5 = 3


@dataclass
class ProxyInfo:
    """
    代理信息

    Attributes:
        url: 代理 URL（如 http://user:pass@host:port）
        protocol: 代理协议
        priority: 优先级（数值越小优先级越高）
        enabled: 是否启用
        last_check: 上次检查时间
        is_healthy: 是否健康
        fail_count: 连续失败次数
        success_count: 成功次数
        avg_response_time: 平均响应时间（秒）
    """
    url: str
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    priority: int = 10
    enabled: bool = True
    last_check: Optional[datetime] = None
    is_healthy: bool = True
    fail_count: int = 0
    success_count: int = 0
    avg_response_time: float = 0.0
    _response_times: list[float] = field(default_factory=list, repr=False)

    @property
    def host(self) -> str:
        """获取代理主机地址"""
        parsed = urlparse(self.url)
        return parsed.hostname or ""

    @property
    def port(self) -> int:
        """获取代理端口"""
        parsed = urlparse(self.url)
        return parsed.port or 80

    @property
    def address(self) -> str:
        """获取代理地址（host:port 格式）"""
        return f"{self.host}:{self.port}"

    def update_response_time(self, response_time: float) -> None:
        """更新响应时间统计"""
        self._response_times.append(response_time)
        # 只保留最近 10 次的响应时间
        if len(self._response_times) > 10:
            self._response_times = self._response_times[-10:]
        self.avg_response_time = sum(self._response_times) / len(self._response_times)


class ProxyHealthChecker(Protocol):
    """代理健康检查器协议"""

    async def check(self, proxy: ProxyInfo) -> bool:
        """
        检查代理是否可用

        Args:
            proxy: 代理信息

        Returns:
            代理是否健康
        """
        ...


class DefaultHealthChecker:
    """默认健康检查器（仅检查连接）"""

    def __init__(self, timeout: float = 5.0, test_url: str = "http://httpbin.org/ip"):
        """
        初始化健康检查器

        Args:
            timeout: 连接超时时间（秒）
            test_url: 测试 URL
        """
        self.timeout = timeout
        self.test_url = test_url

    async def check(self, proxy: ProxyInfo) -> bool:
        """
        检查代理是否可用

        注意：这是一个基础实现，实际使用时应该使用 aiohttp 或 httpx
        进行真实的代理连接测试。

        Args:
            proxy: 代理信息

        Returns:
            代理是否健康
        """
        try:
            # 使用 asyncio 检查端口连通性
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy.host, proxy.port),
                timeout=self.timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return False


@dataclass
class ProxyPoolConfig:
    """代理池配置"""
    # 健康检查间隔（秒）
    health_check_interval: float = 300.0
    # 最大失败次数，超过后禁用代理
    max_fail_count: int = 3
    # 失败后重试的冷却时间（秒）
    retry_cooldown: float = 60.0
    # 是否启用健康检查
    enable_health_check: bool = True
    # 健康检查超时时间
    health_check_timeout: float = 10.0
    # 选择策略：'random'、'priority'、'fastest'
    selection_strategy: Literal["random", "priority", "fastest"] = "priority"


class ProxyPool:
    """
    代理池

    管理代理服务器列表，支持健康检查、优先级排序和失效代理移除。

    Features:
        - 支持从文件/环境变量加载代理列表
        - 支持代理健康检查
        - 支持代理优先级
        - 支持多种选择策略
        - 支持失效代理自动移除

    Example:
        >>> pool = ProxyPool()
        >>> pool.load_from_env("HTTP_PROXY")
        >>> proxy = await pool.get()
        >>> if proxy:
        ...     print(f"Using proxy: {proxy.address}")
    """

    def __init__(
        self,
        config: Optional[ProxyPoolConfig] = None,
        health_checker: Optional[ProxyHealthChecker] = None,
    ) -> None:
        """
        初始化代理池

        Args:
            config: 代理池配置
            health_checker: 健康检查器
        """
        self.config = config or ProxyPoolConfig()
        self.health_checker = health_checker or DefaultHealthChecker(
            timeout=self.config.health_check_timeout
        )
        self._proxies: list[ProxyInfo] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None

    def add(
        self,
        url: str,
        protocol: ProxyProtocol = ProxyProtocol.HTTP,
        priority: int = 10,
    ) -> None:
        """
        添加代理

        Args:
            url: 代理 URL
            protocol: 代理协议
            priority: 优先级（数值越小优先级越高）
        """
        proxy = ProxyInfo(
            url=url,
            protocol=protocol,
            priority=priority,
        )
        self._proxies.append(proxy)

    def remove(self, url: str) -> bool:
        """
        移除代理

        Args:
            url: 代理 URL

        Returns:
            是否成功移除
        """
        for i, proxy in enumerate(self._proxies):
            if proxy.url == url:
                self._proxies.pop(i)
                return True
        return False

    def load_from_list(self, proxy_list: list[str]) -> int:
        """
        从列表加载代理

        Args:
            proxy_list: 代理 URL 列表

        Returns:
            加载的代理数量
        """
        count = 0
        for url in proxy_list:
            url = url.strip()
            if url:
                self.add(url)
                count += 1
        return count

    def load_from_file(self, file_path: str) -> int:
        """
        从文件加载代理

        文件格式：每行一个代理 URL

        Args:
            file_path: 文件路径

        Returns:
            加载的代理数量
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return self.load_from_list(lines)
        except FileNotFoundError:
            return 0

    def load_from_env(self, env_var: str = "HTTP_PROXY") -> int:
        """
        从环境变量加载代理

        支持格式：
        - 单个代理：http://host:port
        - 多个代理：http://host1:port1,http://host2:port2

        Args:
            env_var: 环境变量名

        Returns:
            加载的代理数量
        """
        value = os.environ.get(env_var, "")
        if not value:
            return 0

        # 分割多个代理
        proxies = [p.strip() for p in value.split(",")]
        return self.load_from_list(proxies)

    async def get(self) -> Optional[ProxyInfo]:
        """
        获取可用代理

        根据配置的选择策略选择代理。

        Returns:
            可用的代理信息，如果没有可用代理则返回 None
        """
        async with self._lock:
            available = [p for p in self._proxies if p.enabled and p.is_healthy]

            if not available:
                # 尝试使用冷却中的代理
                available = [
                    p for p in self._proxies
                    if p.enabled and self._is_cooled_down(p)
                ]

            if not available:
                return None

            # 根据策略选择代理
            if self.config.selection_strategy == "random":
                return random.choice(available)
            elif self.config.selection_strategy == "priority":
                return min(available, key=lambda p: p.priority)
            elif self.config.selection_strategy == "fastest":
                return min(available, key=lambda p: p.avg_response_time or float("inf"))
            else:
                return available[0]

    def _is_cooled_down(self, proxy: ProxyInfo) -> bool:
        """检查代理是否已冷却"""
        if proxy.last_check is None:
            return True
        elapsed = (datetime.now() - proxy.last_check).total_seconds()
        return elapsed >= self.config.retry_cooldown

    async def record_success(self, proxy: ProxyInfo, response_time: float = 0.0) -> None:
        """
        记录代理使用成功

        Args:
            proxy: 代理信息
            response_time: 响应时间
        """
        async with self._lock:
            proxy.fail_count = 0
            proxy.success_count += 1
            proxy.is_healthy = True
            if response_time > 0:
                proxy.update_response_time(response_time)

    async def record_failure(self, proxy: ProxyInfo) -> None:
        """
        记录代理使用失败

        Args:
            proxy: 代理信息
        """
        async with self._lock:
            proxy.fail_count += 1
            proxy.last_check = datetime.now()

            if proxy.fail_count >= self.config.max_fail_count:
                proxy.is_healthy = False
                proxy.enabled = False

    async def check_health(self, proxy: ProxyInfo) -> bool:
        """
        检查单个代理健康状态

        Args:
            proxy: 代理信息

        Returns:
            代理是否健康
        """
        is_healthy = await self.health_checker.check(proxy)
        proxy.last_check = datetime.now()
        proxy.is_healthy = is_healthy

        if is_healthy:
            proxy.fail_count = 0
        else:
            proxy.fail_count += 1

        return is_healthy

    async def check_all_health(self) -> dict[str, int]:
        """
        检查所有代理健康状态

        Returns:
            包含健康和不健康代理数量的字典
        """
        tasks = [self.check_health(p) for p in self._proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy = sum(1 for r in results if r is True)
        unhealthy = len(results) - healthy

        return {"healthy": healthy, "unhealthy": unhealthy}

    def start_health_check_loop(self) -> None:
        """启动后台健康检查任务"""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def stop_health_check_loop(self) -> None:
        """停止后台健康检查任务"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            await asyncio.sleep(self.config.health_check_interval)
            await self.check_all_health()

    @property
    def count(self) -> int:
        """代理总数"""
        return len(self._proxies)

    @property
    def healthy_count(self) -> int:
        """健康代理数量"""
        return sum(1 for p in self._proxies if p.is_healthy)

    @property
    def enabled_count(self) -> int:
        """启用代理数量"""
        return sum(1 for p in self._proxies if p.enabled)

    def get_stats(self) -> dict:
        """
        获取代理池统计信息

        Returns:
            包含各类统计数据的字典
        """
        return {
            "total": self.count,
            "healthy": self.healthy_count,
            "enabled": self.enabled_count,
            "unhealthy": self.count - self.healthy_count,
            "proxies": [
                {
                    "address": p.address,
                    "priority": p.priority,
                    "is_healthy": p.is_healthy,
                    "fail_count": p.fail_count,
                    "success_count": p.success_count,
                    "avg_response_time": p.avg_response_time,
                }
                for p in self._proxies
            ],
        }

    def clear(self) -> None:
        """清空代理池"""
        self._proxies.clear()

    def __len__(self) -> int:
        return len(self._proxies)

    def __contains__(self, url: str) -> bool:
        return any(p.url == url for p in self._proxies)
