"""
请求限流中间件

基于令牌桶算法实现请求限流，支持随机延迟模拟人类行为。
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimiterConfig:
    """限流器配置"""

    # 每秒请求数（令牌生成速率）
    requests_per_second: float = 10.0
    # 桶容量（最大令牌数）
    bucket_capacity: float = 10.0
    # 是否启用随机延迟
    enable_jitter: bool = True
    # 随机延迟范围（秒）
    jitter_range: tuple[float, float] = (0.1, 0.5)
    # 最小请求间隔（秒）
    min_interval: float = 0.0


class RateLimiter:
    """
    请求限流器

    基于令牌桶算法实现请求限流，支持随机延迟模拟人类行为。

    令牌桶算法原理：
    - 桶以恒定速率生成令牌
    - 每个请求需要消耗一个令牌
    - 桶满时令牌溢出
    - 桶空时请求需要等待

    Attributes:
        config: 限流器配置

    Example:
        >>> limiter = RateLimiter(requests_per_second=5)
        >>> await limiter.wait()  # 等待可用令牌
        >>> # 执行请求...
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        bucket_capacity: Optional[float] = None,
        enable_jitter: bool = True,
        jitter_range: tuple[float, float] = (0.1, 0.5),
        min_interval: float = 0.0,
        config: Optional[RateLimiterConfig] = None,
    ) -> None:
        """
        初始化限流器

        Args:
            requests_per_second: 每秒请求数（令牌生成速率）
            bucket_capacity: 桶容量，默认等于 requests_per_second
            enable_jitter: 是否启用随机延迟
            jitter_range: 随机延迟范围（秒）
            min_interval: 最小请求间隔（秒）
            config: 配置对象，若提供则忽略其他参数
        """
        if config:
            self.config = config
        else:
            self.config = RateLimiterConfig(
                requests_per_second=requests_per_second,
                bucket_capacity=bucket_capacity or requests_per_second,
                enable_jitter=enable_jitter,
                jitter_range=jitter_range,
                min_interval=min_interval,
            )

        # 令牌桶状态
        self._tokens: float = self.config.bucket_capacity
        self._last_update: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

        # 统计信息
        self._total_requests: int = 0
        self._total_wait_time: float = 0.0

    def _refill_tokens(self) -> None:
        """重新填充令牌"""
        now = time.monotonic()
        elapsed = now - self._last_update

        # 计算新生成的令牌数
        new_tokens = elapsed * self.config.requests_per_second

        # 更新令牌数（不超过桶容量）
        self._tokens = min(
            self.config.bucket_capacity,
            self._tokens + new_tokens
        )
        self._last_update = now

    async def wait(self) -> float:
        """
        等待获取令牌

        如果桶中有令牌则立即返回，否则等待令牌生成。

        Returns:
            实际等待时间（秒）

        Example:
            >>> limiter = RateLimiter(requests_per_second=10)
            >>> wait_time = await limiter.wait()
            >>> print(f"等待了 {wait_time} 秒")
        """
        async with self._lock:
            self._refill_tokens()

            wait_time = 0.0

            if self._tokens < 1.0:
                # 计算需要等待的时间
                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self.config.requests_per_second

                # 确保不超过最小间隔
                if self.config.min_interval > 0:
                    wait_time = max(wait_time, self.config.min_interval)

                await asyncio.sleep(wait_time)

                # 等待后重新计算令牌
                self._refill_tokens()

            # 消耗一个令牌
            self._tokens -= 1.0
            self._total_requests += 1
            self._total_wait_time += wait_time

            # 添加随机延迟（模拟人类行为）
            if self.config.enable_jitter:
                jitter = random.uniform(*self.config.jitter_range)
                await asyncio.sleep(jitter)
                wait_time += jitter

            return wait_time

    def try_acquire(self) -> bool:
        """
        尝试获取令牌（非阻塞）

        Returns:
            是否成功获取令牌
        """
        self._refill_tokens()

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            self._total_requests += 1
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """当前可用令牌数"""
        self._refill_tokens()
        return self._tokens

    @property
    def stats(self) -> dict:
        """
        获取统计信息

        Returns:
            包含总请求数、总等待时间、平均等待时间的字典
        """
        avg_wait = (
            self._total_wait_time / self._total_requests
            if self._total_requests > 0
            else 0.0
        )
        return {
            "total_requests": self._total_requests,
            "total_wait_time": self._total_wait_time,
            "average_wait_time": avg_wait,
            "current_tokens": self._tokens,
        }

    def reset(self) -> None:
        """重置限流器状态"""
        self._tokens = self.config.bucket_capacity
        self._last_update = time.monotonic()
        self._total_requests = 0
        self._total_wait_time = 0.0

    async def __aenter__(self) -> "RateLimiter":
        """异步上下文管理器入口"""
        await self.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        pass
