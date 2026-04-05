"""
重试策略中间件

实现指数退避重试策略，支持抖动避免惊群效应。
"""

import asyncio
import functools
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar, Union

T = TypeVar("T")


@dataclass
class RetryConfig:
    """重试配置"""
    # 最大重试次数
    max_retries: int = 3
    # 基础延迟（秒）
    base_delay: float = 1.0
    # 最大延迟（秒）
    max_delay: float = 60.0
    # 指数退避基数
    exponential_base: float = 2.0
    # 抖动因子（0.0-1.0）
    jitter_factor: float = 0.1
    # 是否添加抖动
    enable_jitter: bool = True
    # 抖动类型：'full'（完全随机）或 'equal'（等抖动）
    jitter_type: str = "equal"
    # 重试前回调
    on_retry: Optional[Callable[[int, Exception, float], None]] = None


class RetryExhaustedError(Exception):
    """重试耗尽错误"""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


class RetryPolicy:
    """
    重试策略

    实现指数退避重试策略，支持抖动避免惊群效应。

    指数退避算法：
        delay = base_delay * (exponential_base ^ attempt)

    抖动类型：
        - equal: delay * (1 + jitter_factor * random())
        - full: random() * delay

    Example:
        >>> policy = RetryPolicy(max_retries=3, base_delay=1.0)
        >>> result = await policy.execute(some_async_function, arg1, arg2)
        >>>
        >>> # 使用装饰器
        >>> @retry(max_retries=3)
        ... async def my_function():
        ...     return await some_api_call()
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter_factor: float = 0.1,
        enable_jitter: bool = True,
        jitter_type: str = "equal",
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
        config: Optional[RetryConfig] = None,
    ) -> None:
        """
        初始化重试策略

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数退避基数
            jitter_factor: 抖动因子（0.0-1.0）
            enable_jitter: 是否启用抖动
            jitter_type: 抖动类型
            on_retry: 重试前回调
            config: 配置对象
        """
        self.config = config or RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter_factor=jitter_factor,
            enable_jitter=enable_jitter,
            jitter_type=jitter_type,
            on_retry=on_retry,
        )

        # 统计信息
        self._total_attempts: int = 0
        self._total_retries: int = 0
        self._total_success_after_retry: int = 0

    def calculate_delay(self, attempt: int) -> float:
        """
        计算第 N 次重试的延迟时间

        Args:
            attempt: 当前重试次数（从 1 开始）

        Returns:
            延迟时间（秒）
        """
        # 指数退避
        delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))

        # 限制最大延迟
        delay = min(delay, self.config.max_delay)

        # 添加抖动
        if self.config.enable_jitter:
            delay = self._add_jitter(delay)

        return delay

    def _add_jitter(self, delay: float) -> float:
        """添加抖动"""
        if self.config.jitter_type == "full":
            # 完全随机：0 ~ delay
            return random.random() * delay
        else:
            # 等抖动：delay * (1 + jitter_factor * random())
            jitter = delay * self.config.jitter_factor * random.random()
            return delay + jitter

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        exceptions: Union[type[Exception], tuple[type[Exception], ...]] = Exception,
        **kwargs: Any,
    ) -> T:
        """
        执行带有重试策略的函数

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            exceptions: 要捕获的异常类型
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            RetryExhaustedError: 重试耗尽后仍失败
        """
        last_exception: Optional[Exception] = None
        attempt = 0

        while attempt <= self.config.max_retries:
            self._total_attempts += 1

            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    self._total_success_after_retry += 1
                return result
            except exceptions as e:
                last_exception = e
                attempt += 1

                if attempt > self.config.max_retries:
                    break

                self._total_retries += 1
                delay = self.calculate_delay(attempt)

                # 调用重试回调
                if self.config.on_retry:
                    self.config.on_retry(attempt, e, delay)

                await asyncio.sleep(delay)

        raise RetryExhaustedError(
            f"Retry exhausted after {attempt} attempts",
            attempts=attempt,
            last_exception=last_exception,
        )

    def decorate(
        self,
        exceptions: Union[type[Exception], tuple[type[Exception], ...]] = Exception,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        返回一个装饰器，用于装饰异步函数

        Args:
            exceptions: 要捕获的异常类型

        Returns:
            装饰器函数

        Example:
            >>> policy = RetryPolicy(max_retries=3)
            >>> @policy.decorate()
            ... async def my_function():
            ...     return await some_api_call()
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                return await self.execute(func, *args, exceptions=exceptions, **kwargs)
            return wrapper
        return decorator

    @property
    def stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_attempts": self._total_attempts,
            "total_retries": self._total_retries,
            "success_after_retry": self._total_success_after_retry,
            "retry_rate": (
                self._total_retries / self._total_attempts
                if self._total_attempts > 0
                else 0.0
            ),
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._total_attempts = 0
        self._total_retries = 0
        self._total_success_after_retry = 0


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter_factor: float = 0.1,
    enable_jitter: bool = True,
    jitter_type: str = "equal",
    exceptions: Union[type[Exception], tuple[type[Exception], ...]] = Exception,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    重试装饰器

    为异步函数添加重试功能。

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数退避基数
        jitter_factor: 抖动因子
        enable_jitter: 是否启用抖动
        jitter_type: 抖动类型
        exceptions: 要捕获的异常类型
        on_retry: 重试前回调

    Returns:
        装饰器函数

    Example:
        >>> @retry(max_retries=3, base_delay=1.0)
        ... async def fetch_data():
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get(url) as response:
        ...             return await response.json()

        >>> # 指定异常类型
        >>> @retry(max_retries=3, exceptions=(ConnectionError, TimeoutError))
        ... async def connect():
        ...     return await establish_connection()
    """
    policy = RetryPolicy(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter_factor=jitter_factor,
        enable_jitter=enable_jitter,
        jitter_type=jitter_type,
        on_retry=on_retry,
    )
    return policy.decorate(exceptions)


class RetryContext:
    """
    重试上下文管理器

    用于手动控制重试流程。

    Example:
        >>> async with RetryContext(max_retries=3) as ctx:
        ...     while ctx.should_retry():
        ...         try:
        ...             result = await some_operation()
        ...             ctx.success()
        ...             break
        ...         except Exception as e:
        ...             await ctx.failure(e)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter_factor: float = 0.1,
        enable_jitter: bool = True,
    ) -> None:
        self._policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter_factor=jitter_factor,
            enable_jitter=enable_jitter,
        )
        self._attempt: int = 0
        self._success: bool = False
        self._last_exception: Optional[Exception] = None

    @property
    def attempt(self) -> int:
        """当前尝试次数"""
        return self._attempt

    @property
    def last_exception(self) -> Optional[Exception]:
        """最后一次异常"""
        return self._last_exception

    @property
    def is_success(self) -> bool:
        """是否成功"""
        return self._success

    def should_retry(self) -> bool:
        """是否应该继续重试"""
        return not self._success and self._attempt <= self._policy.config.max_retries

    def success(self) -> None:
        """标记成功"""
        self._success = True

    async def failure(self, exception: Exception) -> None:
        """
        标记失败并等待

        Args:
            exception: 发生的异常
        """
        self._last_exception = exception
        self._attempt += 1

        if self.should_retry():
            delay = self._policy.calculate_delay(self._attempt)
            await asyncio.sleep(delay)

    async def __aenter__(self) -> "RetryContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
