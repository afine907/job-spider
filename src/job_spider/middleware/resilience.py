"""
弹性调用客户端 - 融合重试、熔断、限流

提供统一的弹性调用封装，确保重试与熔断器正确联动。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from job_spider.middleware.retry import RetryConfig, RetryPolicy, RetryExhaustedError
from job_spider.middleware.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState
from job_spider.middleware.rate_limiter import RateLimiter


@dataclass
class ResilienceMetrics:
    """弹性调用指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    circuit_rejected: int = 0
    rate_limited: int = 0
    total_latency: float = 0.0

    def record_success(self, latency: float, retries: int = 0) -> None:
        """记录成功请求"""
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency += latency
        if retries > 0:
            self.retried_requests += 1

    def record_failure(self) -> None:
        """记录失败请求"""
        self.total_requests += 1
        self.failed_requests += 1

    def record_circuit_rejected(self) -> None:
        """记录熔断拒绝"""
        self.circuit_rejected += 1
        self.total_requests += 1

    def record_rate_limited(self) -> None:
        """记录限流等待"""
        self.rate_limited += 1

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def average_latency(self) -> float:
        """平均延迟"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency / self.successful_requests


class ResilientClient:
    """
    融合重试与熔断的弹性客户端

    提供统一的弹性调用封装，确保重试与熔断器正确联动。

    工作流程:
    1. 检查熔断器状态（如果开启则直接抛出异常）
    2. 获取限流令牌（等待限流）
    3. 执行请求（带重试）
    4. 记录成功/失败到熔断器
    5. 收集指标

    Attributes:
        retry_config: 重试配置
        circuit_breaker: 熔断器实例
        rate_limiter: 限流器实例
        metrics: 弹性调用指标

    Example:
        >>> client = ResilientClient(
        ...     retry_config=RetryConfig(max_retries=3),
        ...     circuit_breaker=CircuitBreaker(name="api"),
        ...     rate_limiter=RateLimiter(requests_per_second=10),
        ... )
        ...
        >>> async def fetch_data():
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get(url) as response:
        ...             return await response.json()
        ...
        >>> result = await client.request(fetch_data)

        # 或者使用上下文管理器
        >>> async with ResilientClient() as client:
        ...     result = await client.request(some_async_func, arg1, arg2)
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        rate_limiter: Optional[RateLimiter] = None,
        name: str = "default",
    ) -> None:
        """
        初始化弹性客户端

        Args:
            retry_config: 重试配置，None 表示不重试
            circuit_breaker: 熔断器实例，None 表示不使用熔断
            rate_limiter: 限流器实例，None 表示不限流
            name: 客户端名称，用于日志和指标标识
        """
        self.name = name
        self.retry_config = retry_config
        self.circuit_breaker = circuit_breaker
        self.rate_limiter = rate_limiter
        self.metrics = ResilienceMetrics()

        # 创建重试策略实例
        self._retry_policy: Optional[RetryPolicy] = None
        if retry_config:
            self._retry_policy = RetryPolicy(config=retry_config)

        # 锁用于线程安全
        self._lock = asyncio.Lock()

    async def request(
        self,
        func: Callable[..., Any],
        *args: Any,
        exceptions: Union[type[Exception], tuple[type[Exception], ...]] = Exception,
        **kwargs: Any,
    ) -> Any:
        """
        执行弹性请求

        流程:
        1. 检查熔断器状态（如果开启则直接抛出异常）
        2. 获取限流令牌（等待限流）
        3. 执行请求（带重试）
        4. 记录成功/失败到熔断器
        5. 收集指标

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            exceptions: 要捕获的异常类型，用于重试判断
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerError: 熔断器处于打开状态时
            RetryExhaustedError: 重试耗尽后仍失败
        """
        start_time = time.monotonic()
        retries = 0

        # 1. 检查熔断器状态
        if self.circuit_breaker:
            if not self.circuit_breaker.can_execute():
                self.metrics.record_circuit_rejected()
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.circuit_breaker.name}' is open. "
                    f"Request rejected without retry."
                )

        # 2. 获取限流令牌
        if self.rate_limiter:
            await self.rate_limiter.wait()
            self.metrics.record_rate_limited()

        # 3. 执行请求（带重试）
        last_exception: Optional[Exception] = None
        attempt = 0
        max_attempts = 1

        if self._retry_policy:
            max_attempts = self._retry_policy.config.max_retries + 1

        while attempt < max_attempts:
            attempt += 1

            try:
                result = await func(*args, **kwargs)

                # 4. 记录成功到熔断器
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()

                # 5. 收集指标
                latency = time.monotonic() - start_time
                self.metrics.record_success(latency, retries)

                return result

            except exceptions as e:
                last_exception = e
                retries += 1

                # 检查熔断器状态（可能在重试期间被其他请求打开）
                if self.circuit_breaker and not self.circuit_breaker.can_execute():
                    # 熔断器被打开，停止重试
                    self.metrics.record_failure()
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.circuit_breaker.name}' opened during retry. "
                        f"Stopping retry after {attempt} attempts."
                    ) from e

                # 计算重试延迟
                if self._retry_policy and attempt < max_attempts:
                    delay = self._retry_policy.calculate_delay(attempt)

                    # 调用重试回调
                    if self._retry_policy.config.on_retry:
                        self._retry_policy.config.on_retry(attempt, e, delay)

                    await asyncio.sleep(delay)

        # 重试耗尽，记录失败到熔断器
        if self.circuit_breaker:
            self.circuit_breaker.record_failure()

        self.metrics.record_failure()

        raise RetryExhaustedError(
            f"Request failed after {attempt} attempts",
            attempts=attempt,
            last_exception=last_exception,
        )

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        执行弹性请求（简化版本）

        这是 request 方法的简化版本，使用默认异常类型。

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值
        """
        return await self.request(func, *args, **kwargs)

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            包含各类统计信息的字典
        """
        stats = {
            "name": self.name,
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "successful_requests": self.metrics.successful_requests,
                "failed_requests": self.metrics.failed_requests,
                "retried_requests": self.metrics.retried_requests,
                "circuit_rejected": self.metrics.circuit_rejected,
                "rate_limited": self.metrics.rate_limited,
                "success_rate": self.metrics.success_rate,
                "average_latency": self.metrics.average_latency,
            },
        }

        if self.circuit_breaker:
            stats["circuit_breaker"] = {
                "name": self.circuit_breaker.name,
                "state": self.circuit_breaker.state.value,
                "stats": {
                    "total_calls": self.circuit_breaker.stats.total_calls,
                    "successful_calls": self.circuit_breaker.stats.successful_calls,
                    "failed_calls": self.circuit_breaker.stats.failed_calls,
                    "rejected_calls": self.circuit_breaker.stats.rejected_calls,
                },
            }

        if self.rate_limiter:
            stats["rate_limiter"] = self.rate_limiter.stats

        if self._retry_policy:
            stats["retry"] = self._retry_policy.stats

        return stats

    def reset_stats(self) -> None:
        """重置所有统计信息"""
        self.metrics = ResilienceMetrics()

        if self.circuit_breaker:
            self.circuit_breaker.reset()

        if self.rate_limiter:
            self.rate_limiter.reset()

        if self._retry_policy:
            self._retry_policy.reset_stats()

    async def __aenter__(self) -> "ResilientClient":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        pass

    def __repr__(self) -> str:
        parts = [f"ResilientClient(name={self.name!r}"]

        if self.circuit_breaker:
            parts.append(f"circuit_breaker={self.circuit_breaker.state.value}")

        if self._retry_policy:
            parts.append(f"max_retries={self._retry_policy.config.max_retries}")

        if self.rate_limiter:
            parts.append(f"rate={self.rate_limiter.config.requests_per_second}/s")

        parts.append(")")
        return " ".join(parts)


class ResilientClientBuilder:
    """
    弹性客户端构建器

    提供流式 API 构建 ResilientClient 实例。

    Example:
        >>> client = (
        ...     ResilientClientBuilder()
        ...     .with_name("api_client")
        ...     .with_retry(max_retries=3, base_delay=1.0)
        ...     .with_circuit_breaker(name="api", failure_threshold=5)
        ...     .with_rate_limiter(requests_per_second=10)
        ...     .build()
        ... )
    """

    def __init__(self) -> None:
        """初始化构建器"""
        self._name: str = "default"
        self._retry_config: Optional[RetryConfig] = None
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._rate_limiter: Optional[RateLimiter] = None

    def with_name(self, name: str) -> "ResilientClientBuilder":
        """
        设置客户端名称

        Args:
            name: 客户端名称

        Returns:
            Self for chaining
        """
        self._name = name
        return self

    def with_retry(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter_factor: float = 0.1,
        enable_jitter: bool = True,
        jitter_type: str = "equal",
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    ) -> "ResilientClientBuilder":
        """
        配置重试策略

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数退避基数
            jitter_factor: 抖动因子
            enable_jitter: 是否启用抖动
            jitter_type: 抖动类型
            on_retry: 重试前回调

        Returns:
            Self for chaining
        """
        self._retry_config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter_factor=jitter_factor,
            enable_jitter=enable_jitter,
            jitter_type=jitter_type,
            on_retry=on_retry,
        )
        return self

    def with_circuit_breaker(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        success_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> "ResilientClientBuilder":
        """
        配置熔断器

        Args:
            name: 熔断器名称
            failure_threshold: 失败阈值
            success_threshold: 成功阈值
            recovery_timeout: 恢复超时时间（秒）

        Returns:
            Self for chaining
        """
        self._circuit_breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            recovery_timeout=recovery_timeout,
        )
        return self

    def with_rate_limiter(
        self,
        requests_per_second: float = 10.0,
        bucket_capacity: Optional[float] = None,
        enable_jitter: bool = True,
    ) -> "ResilientClientBuilder":
        """
        配置限流器

        Args:
            requests_per_second: 每秒请求数
            bucket_capacity: 桶容量
            enable_jitter: 是否启用随机延迟

        Returns:
            Self for chaining
        """
        self._rate_limiter = RateLimiter(
            requests_per_second=requests_per_second,
            bucket_capacity=bucket_capacity,
            enable_jitter=enable_jitter,
        )
        return self

    def build(self) -> ResilientClient:
        """
        构建 ResilientClient 实例

        Returns:
            配置好的 ResilientClient 实例
        """
        return ResilientClient(
            name=self._name,
            retry_config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
            rate_limiter=self._rate_limiter,
        )
