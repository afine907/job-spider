"""
熔断器中间件

实现熔断器模式，防止级联故障。
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态，允许请求通过
    OPEN = "open"          # 熔断状态，拒绝所有请求
    HALF_OPEN = "half_open"  # 半开状态，允许部分请求通过以测试服务恢复


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    # 失败阈值，达到后触发熔断
    failure_threshold: int = 5
    # 成功阈值，半开状态下达到后恢复为关闭状态
    success_threshold: int = 3
    # 熔断持续时间（秒），之后进入半开状态
    recovery_timeout: float = 30.0
    # 半开状态下允许的最大请求数
    half_open_max_calls: int = 1
    # 失败率阈值（0.0-1.0），配合最小请求数使用
    failure_rate_threshold: float = 0.5
    # 计算失败率的最小请求数
    minimum_number_of_calls: int = 10
    # 滑动窗口大小（秒），用于计算失败率
    sliding_window_size: float = 60.0


@dataclass
class CircuitStats:
    """熔断器统计信息"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_transitions: int = 0
    last_failure_time: Optional[float] = None
    last_state_change_time: Optional[float] = None
    # 滑动窗口内的调用记录
    _calls: list[tuple[float, bool]] = field(default_factory=list, repr=False)

    def record_call(self, success: bool, window_size: float) -> None:
        """记录一次调用"""
        now = time.monotonic()
        self._calls.append((now, success))
        self.total_calls += 1

        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            self.last_failure_time = now

        # 清理过期的调用记录
        cutoff = now - window_size
        self._calls = [(t, s) for t, s in self._calls if t > cutoff]

    def get_failure_rate(self) -> float:
        """计算滑动窗口内的失败率"""
        if not self._calls:
            return 0.0
        failures = sum(1 for _, success in self._calls if not success)
        return failures / len(self._calls)

    def get_recent_calls_count(self) -> int:
        """获取滑动窗口内的调用次数"""
        return len(self._calls)


class CircuitBreakerError(Exception):
    """熔断器错误"""
    pass


class CircuitBreaker:
    """
    熔断器

    实现熔断器模式，在服务故障时快速失败，防止级联故障。

    三种状态：
    - CLOSED: 正常状态，允许请求通过
    - OPEN: 熔断状态，拒绝所有请求
    - HALF_OPEN: 半开状态，允许部分请求通过以测试服务恢复

    状态转换：
    - CLOSED -> OPEN: 失败次数/失败率达到阈值
    - OPEN -> HALF_OPEN: 熔断时间结束
    - HALF_OPEN -> CLOSED: 成功次数达到阈值
    - HALF_OPEN -> OPEN: 再次失败

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        >>> async with breaker:
        ...     result = await some_api_call()
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        success_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        failure_rate_threshold: float = 0.5,
        minimum_number_of_calls: int = 10,
        sliding_window_size: float = 60.0,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        """
        初始化熔断器

        Args:
            name: 熔断器名称
            failure_threshold: 失败阈值
            success_threshold: 成功阈值
            recovery_timeout: 恢复超时时间（秒）
            half_open_max_calls: 半开状态最大请求数
            failure_rate_threshold: 失败率阈值
            minimum_number_of_calls: 最小请求数
            sliding_window_size: 滑动窗口大小
            config: 配置对象
        """
        self.name = name
        self.config = config or CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            failure_rate_threshold=failure_rate_threshold,
            minimum_number_of_calls=minimum_number_of_calls,
            sliding_window_size=sliding_window_size,
        )

        self._state: CircuitState = CircuitState.CLOSED
        self._stats: CircuitStats = CircuitStats()
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._half_open_calls: int = 0
        self._last_state_change: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

        # 状态变化回调
        self._on_state_change: Optional[Callable[[CircuitState, CircuitState], None]] = None

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态"""
        self._check_state_transition()
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """获取统计信息"""
        return self._stats

    @property
    def is_closed(self) -> bool:
        """是否处于关闭状态"""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """是否处于熔断状态"""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """是否处于半开状态"""
        return self.state == CircuitState.HALF_OPEN

    def _check_state_transition(self) -> None:
        """检查是否需要进行状态转换"""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.config.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """状态转换"""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.monotonic()
        self._stats.state_transitions += 1
        self._stats.last_state_change_time = self._last_state_change

        # 重置状态相关计数器
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._consecutive_successes = 0

        # 触发回调
        if self._on_state_change:
            self._on_state_change(old_state, new_state)

    def record_success(self) -> None:
        """
        记录成功调用

        在成功调用后更新熔断器状态。
        """
        self._stats.record_call(True, self.config.sliding_window_size)
        self._consecutive_failures = 0
        self._consecutive_successes += 1

        if self._state == CircuitState.HALF_OPEN:
            if self._consecutive_successes >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """
        记录失败调用

        在失败调用后更新熔断器状态。
        """
        self._stats.record_call(False, self.config.sliding_window_size)
        self._consecutive_failures += 1
        self._consecutive_successes = 0

        if self._state == CircuitState.CLOSED:
            # 检查是否达到失败阈值
            if self._consecutive_failures >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
            # 检查是否达到失败率阈值
            elif (
                self._stats.get_recent_calls_count() >= self.config.minimum_number_of_calls
                and self._stats.get_failure_rate() >= self.config.failure_rate_threshold
            ):
                self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.HALF_OPEN:
            # 半开状态下任何失败都会重新熔断
            self._transition_to(CircuitState.OPEN)

    def can_execute(self) -> bool:
        """
        检查是否允许执行

        Returns:
            是否允许执行请求
        """
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True

        if current_state == CircuitState.OPEN:
            return False

        if current_state == CircuitState.HALF_OPEN:
            # 检查半开状态下的请求数限制
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        执行被熔断器保护的调用

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerError: 熔断器处于打开状态时
        """
        async with self._lock:
            if not self.can_execute():
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Please retry after {self._get_remaining_timeout():.1f} seconds."
                )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self.record_success()
            return result
        except Exception as e:
            async with self._lock:
                self.record_failure()
            raise

    def _get_remaining_timeout(self) -> float:
        """获取剩余熔断时间"""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.monotonic() - self._last_state_change
        return max(0.0, self.config.recovery_timeout - elapsed)

    def on_state_change(
        self, callback: Callable[[CircuitState, CircuitState], None]
    ) -> None:
        """
        设置状态变化回调

        Args:
            callback: 回调函数，接收旧状态和新状态
        """
        self._on_state_change = callback

    def reset(self) -> None:
        """重置熔断器"""
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._half_open_calls = 0
        self._last_state_change = time.monotonic()

    def force_open(self) -> None:
        """强制打开熔断器"""
        self._transition_to(CircuitState.OPEN)

    def force_close(self) -> None:
        """强制关闭熔断器"""
        self._transition_to(CircuitState.CLOSED)

    async def __aenter__(self) -> "CircuitBreaker":
        """异步上下文管理器入口"""
        async with self._lock:
            if not self.can_execute():
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Please retry after {self._get_remaining_timeout():.1f} seconds."
                )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        async with self._lock:
            if exc_type is not None:
                self.record_failure()
            else:
                self.record_success()

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self._state.value}, "
            f"failures={self._consecutive_failures})"
        )
