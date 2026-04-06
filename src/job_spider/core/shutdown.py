"""
优雅关闭模块。

实现信号处理、关闭钩子注册和超时强制退出机制。

关闭流程:
    信号接收 -> 设置关闭标志 -> 等待当前任务完成 -> 执行清理钩子 -> 退出
                              └── 超时强制退出 ──┘

Example:
    >>> from job_spider.core.shutdown import shutdown_manager
    >>>
    >>> # 注册关闭钩子
    >>> @shutdown_manager.register_hook
    ... async def cleanup():
    ...     await db.close()
    ...     await client.aclose()
    >>>
    >>> # 在主程序中设置信号处理
    >>> shutdown_manager.setup_signal_handlers()
"""

import asyncio
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Any

import structlog

logger = structlog.get_logger(__name__)


class ShutdownState(str, Enum):
    """关闭状态枚举。"""

    RUNNING = "running"  # 正常运行
    SHUTTING_DOWN = "shutting_down"  # 正在关闭
    SHUTDOWN = "shutdown"  # 已关闭


@dataclass
class ShutdownStats:
    """关闭统计信息。"""

    active_tasks: int = 0
    completed_hooks: int = 0
    total_hooks: int = 0


HookFunc = Callable[[], Coroutine[Any, Any, None]]


class ShutdownManager:
    """
    优雅关闭管理器。

    负责管理信号处理、关闭钩子注册和优雅关闭流程。

    Attributes:
        state: 当前关闭状态
        timeout: 关闭超时时间（秒）
        hooks: 关闭钩子列表

    Example:
        >>> manager = ShutdownManager(timeout=30.0)
        >>>
        >>> # 注册钩子
        >>> @manager.register_hook
        ... async def cleanup_db():
        ...     await db.close()
        >>>
        >>> # 设置信号处理
        >>> manager.setup_signal_handlers()
        >>>
        >>> # 检查是否应该关闭
        >>> if manager.should_shutdown:
        ...     await manager.shutdown()
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """
        初始化关闭管理器。

        Args:
            timeout: 关闭超时时间（秒），超时后强制退出
        """
        self._state = ShutdownState.RUNNING
        self._timeout = timeout
        self._hooks: list[HookFunc] = []
        self._shutdown_event = asyncio.Event()
        self._active_task_count = 0
        self._lock = asyncio.Lock()
        self._shutdown_started = False

    @property
    def state(self) -> ShutdownState:
        """获取当前关闭状态。"""
        return self._state

    @property
    def should_shutdown(self) -> bool:
        """检查是否应该关闭。"""
        return self._state != ShutdownState.RUNNING

    @property
    def timeout(self) -> float:
        """获取关闭超时时间。"""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        """设置关闭超时时间。"""
        self._timeout = value

    @property
    def active_task_count(self) -> int:
        """获取当前活跃任务数。"""
        return self._active_task_count

    def register_hook(self, hook: HookFunc) -> HookFunc:
        """
        注册关闭钩子。

        Args:
            hook: 异步清理函数

        Returns:
            原始钩子函数（支持装饰器模式）

        Example:
            >>> @shutdown_manager.register_hook
            ... async def cleanup():
            ...     await db.close()
        """
        self._hooks.append(hook)
        logger.debug("关闭钩子已注册", hook=hook.__name__, total_hooks=len(self._hooks))
        return hook

    def unregister_hook(self, hook: HookFunc) -> bool:
        """
        取消注册关闭钩子。

        Args:
            hook: 要取消的钩子函数

        Returns:
            是否成功取消
        """
        try:
            self._hooks.remove(hook)
            logger.debug("关闭钩子已取消", hook=hook.__name__)
            return True
        except ValueError:
            return False

    def setup_signal_handlers(self) -> None:
        """
        设置信号处理器。

        处理 SIGTERM 和 SIGINT 信号，触发优雅关闭流程。
        在 Windows 上，只处理 SIGINT (Ctrl+C)。
        """
        loop = asyncio.get_running_loop()

        def handle_signal(sig: signal.Signals) -> None:
            """信号处理函数。"""
            logger.info(
                "收到关闭信号",
                signal=sig.name,
                state=self._state.value,
            )
            self.request_shutdown()

        # 注册 SIGINT (Ctrl+C)
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: handle_signal(signal.SIGINT))
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            signal.signal(signal.SIGINT, lambda s, f: self.request_shutdown())

        # 注册 SIGTERM (kill 命令)
        try:
            loop.add_signal_handler(signal.SIGTERM, lambda: handle_signal(signal.SIGTERM))
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            try:
                signal.signal(signal.SIGTERM, lambda s, f: self.request_shutdown())
            except (ValueError, OSError):
                # Windows 上 SIGTERM 可能不可用
                pass

        logger.info("信号处理器已设置", signals=["SIGINT", "SIGTERM"])

    def request_shutdown(self) -> None:
        """
        请求关闭。

        设置关闭标志，通知所有等待的任务。
        """
        if self._state != ShutdownState.RUNNING:
            return

        self._state = ShutdownState.SHUTTING_DOWN
        self._shutdown_event.set()

        logger.warning(
            "关闭请求已发出",
            state=self._state.value,
            active_tasks=self._active_task_count,
            hooks=len(self._hooks),
        )

    async def wait_for_shutdown(self) -> None:
        """
        等待关闭信号。

        阻塞直到收到关闭信号。
        """
        await self._shutdown_event.wait()

    async def increment_task(self) -> None:
        """
        增加活跃任务计数。

        用于追踪正在执行的任务数量。
        """
        async with self._lock:
            self._active_task_count += 1
            logger.debug("任务开始", active_tasks=self._active_task_count)

    async def decrement_task(self) -> None:
        """
        减少活跃任务计数。

        用于追踪正在执行的任务数量。
        """
        async with self._lock:
            self._active_task_count = max(0, self._active_task_count - 1)
            logger.debug("任务完成", active_tasks=self._active_task_count)

    def get_stats(self) -> ShutdownStats:
        """
        获取关闭统计信息。

        Returns:
            ShutdownStats: 统计信息
        """
        return ShutdownStats(
            active_tasks=self._active_task_count,
            completed_hooks=0,  # 将在关闭过程中更新
            total_hooks=len(self._hooks),
        )

    async def execute_hooks(self) -> int:
        """
        执行所有关闭钩子。

        Returns:
            成功执行的钩子数量
        """
        completed = 0
        for i, hook in enumerate(self._hooks):
            try:
                logger.info(
                    "执行关闭钩子",
                    hook=hook.__name__,
                    progress=f"{i + 1}/{len(self._hooks)}",
                )
                await hook()
                completed += 1
                logger.debug(
                    "关闭钩子执行成功",
                    hook=hook.__name__,
                )
            except Exception as e:
                logger.error(
                    "关闭钩子执行失败",
                    hook=hook.__name__,
                    error=str(e),
                    exc_info=True,
                )

        return completed

    async def shutdown(self, force: bool = False) -> None:
        """
        执行优雅关闭。

        等待当前任务完成，执行清理钩子，然后退出。

        Args:
            force: 是否强制关闭（不等待任务完成）

        关闭流程:
            1. 设置关闭状态
            2. 等待活跃任务完成（可选）
            3. 执行关闭钩子
            4. 设置完成状态
        """
        if self._shutdown_started:
            return

        self._shutdown_started = True
        self._state = ShutdownState.SHUTTING_DOWN

        logger.info(
            "开始优雅关闭",
            active_tasks=self._active_task_count,
            hooks=len(self._hooks),
            timeout=self._timeout,
        )

        start_time = asyncio.get_event_loop().time()

        try:
            # 等待活跃任务完成（带超时）
            if not force and self._active_task_count > 0:
                wait_time = self._timeout * 0.5  # 用一半时间等待任务
                logger.info(
                    "等待活跃任务完成",
                    active_tasks=self._active_task_count,
                    wait_timeout=wait_time,
                )

                deadline = start_time + wait_time
                while self._active_task_count > 0:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        logger.warning(
                            "等待任务超时，强制继续关闭",
                            remaining_tasks=self._active_task_count,
                        )
                        break
                    await asyncio.sleep(min(0.5, remaining))

            # 执行关闭钩子（带超时）
            remaining_time = self._timeout - (asyncio.get_event_loop().time() - start_time)
            if remaining_time <= 0:
                remaining_time = 5.0  # 至少给钩子 5 秒时间

            logger.info(
                "执行关闭钩子",
                hooks=len(self._hooks),
                timeout=remaining_time,
            )

            try:
                completed = await asyncio.wait_for(
                    self.execute_hooks(),
                    timeout=remaining_time,
                )
                logger.info("关闭钩子执行完成", completed=completed)
            except asyncio.TimeoutError:
                logger.warning("关闭钩子执行超时")

            self._state = ShutdownState.SHUTDOWN
            duration = asyncio.get_event_loop().time() - start_time
            logger.info(
                "优雅关闭完成",
                duration=f"{duration:.2f}s",
                final_active_tasks=self._active_task_count,
            )

        except Exception as e:
            logger.error(
                "优雅关闭出错",
                error=str(e),
                exc_info=True,
            )
            self._state = ShutdownState.SHUTDOWN

    def force_exit(self, code: int = 0) -> None:
        """
        强制退出进程。

        Args:
            code: 退出码
        """
        logger.warning("强制退出", exit_code=code)
        sys.exit(code)


# 全局关闭管理器实例
shutdown_manager = ShutdownManager()


def get_shutdown_manager() -> ShutdownManager:
    """
    获取全局关闭管理器实例。

    Returns:
        ShutdownManager: 全局关闭管理器
    """
    return shutdown_manager


async def run_with_shutdown_check(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    运行协程并检查关闭信号。

    如果收到关闭信号，会取消协程并抛出 CancelledError。

    Args:
        coro: 要运行的协程

    Returns:
        协程的返回值

    Raises:
        asyncio.CancelledError: 如果收到关闭信号
    """
    task = asyncio.create_task(coro)
    shutdown_task = asyncio.create_task(shutdown_manager.wait_for_shutdown())

    done, pending = await asyncio.wait(
        [task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 取消未完成的任务
    for p in pending:
        p.cancel()
        try:
            await p
        except asyncio.CancelledError:
            pass

    if shutdown_task in done:
        # 收到关闭信号
        raise asyncio.CancelledError("Shutdown requested")

    return task.result()
