"""
爬虫引擎模块。

实现爬虫的调度、并发控制和结果收集。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import time

import structlog

from job_spider.spiders.base import BaseSpider, SpiderContext, SpiderRegistry
from job_spider.observability.metrics import SpiderMetrics, metrics
from job_spider.core.shutdown import shutdown_manager

logger = structlog.get_logger(__name__)


class SpiderStatus(str, Enum):
    """爬虫执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class SpiderResult:
    """
    爬虫执行结果。

    Attributes:
        spider_name: 爬虫名称
        status: 执行状态
        data: 爬取的数据
        error: 错误信息
        start_time: 开始时间
        end_time: 结束时间
        duration: 执行耗时（秒）
        metadata: 额外元数据

    Example:
        >>> result = SpiderResult(
        ...     spider_name="boss",
        ...     status=SpiderStatus.SUCCESS,
        ...     data=[{"title": "Python工程师"}],
        ...     duration=1.5,
        ... )
    """

    spider_name: str
    status: SpiderStatus
    data: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """是否执行成功。"""
        return self.status == SpiderStatus.SUCCESS

    @property
    def item_count(self) -> int:
        """爬取的数据条数。"""
        return len(self.data)


@dataclass
class EngineStats:
    """
    引擎执行统计。

    Attributes:
        total_spiders: 总爬虫数
        success_count: 成功数
        failed_count: 失败数
        total_items: 总数据条数
        total_duration: 总耗时（秒）
        active_tasks: 当前活跃任务数
    """

    total_spiders: int = 0
    success_count: int = 0
    failed_count: int = 0
    total_items: int = 0
    total_duration: float = 0.0
    active_tasks: int = 0

    def add_result(self, result: SpiderResult) -> None:
        """添加执行结果到统计。"""
        self.total_spiders += 1
        if result.is_success:
            self.success_count += 1
        else:
            self.failed_count += 1
        self.total_items += result.item_count
        self.total_duration += result.duration


class SpiderEngine:
    """
    爬虫引擎。

    负责爬虫的调度、并发控制和结果收集。

    Attributes:
        registry: 爬虫注册中心
        max_concurrent: 最大并发数
        timeout: 执行超时时间

    Example:
        >>> from config.settings import get_settings
        >>> settings = get_settings()
        >>> engine = SpiderEngine(settings)
        >>>
        >>> # 运行单个爬虫
        >>> result = await engine.run_one("boss", ctx)
        >>>
        >>> # 运行多个爬虫
        >>> results = await engine.run_many(["boss", "lagou"], ctx)
    """

    def __init__(
        self,
        config: Any,  # Settings 类型
        registry: SpiderRegistry | None = None,
    ) -> None:
        """
        初始化爬虫引擎。

        Args:
            config: 配置对象
            registry: 爬虫注册中心，为 None 时使用全局注册中心
        """
        self.config = config
        self.registry = registry or SpiderRegistry
        self.max_concurrent = config.spider.max_concurrent
        self.timeout = config.spider.timeout
        self._stats = EngineStats()
        self._cleanup_done = False

    def get_stats(self) -> EngineStats:
        """
        获取引擎统计信息。

        Returns:
            EngineStats: 当前统计信息
        """
        self._stats.active_tasks = shutdown_manager.active_task_count
        return self._stats

    async def cleanup(self) -> None:
        """
        清理引擎资源。

        等待所有活跃任务完成并释放资源。
        """
        if self._cleanup_done:
            return

        self._cleanup_done = True
        stats = self.get_stats()

        logger.info(
            "引擎清理中",
            active_tasks=stats.active_tasks,
            total_spiders=stats.total_spiders,
            success_count=stats.success_count,
            failed_count=stats.failed_count,
        )

        # 等待活跃任务完成（最多等待 timeout 时间）
        if stats.active_tasks > 0:
            try:
                await asyncio.wait_for(
                    self._wait_for_active_tasks(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "等待活跃任务超时",
                    remaining_tasks=shutdown_manager.active_task_count,
                )

        logger.info("引擎清理完成")

    async def _wait_for_active_tasks(self) -> None:
        """等待所有活跃任务完成。"""
        while shutdown_manager.active_task_count > 0:
            await asyncio.sleep(0.1)

    async def run_one(
        self,
        spider_name: str,
        ctx: SpiderContext,
        timeout: float | None = None,
    ) -> SpiderResult:
        """
        运行单个爬虫。

        Args:
            spider_name: 爬虫名称
            ctx: 爬虫上下文
            timeout: 超时时间，为 None 时使用配置值

        Returns:
            SpiderResult: 执行结果

        Example:
            >>> result = await engine.run_one("boss", ctx)
            >>> if result.is_success:
            ...     print(f"爬取了 {result.item_count} 条数据")
        """
        # 检查是否应该关闭
        if shutdown_manager.should_shutdown:
            return SpiderResult(
                spider_name=spider_name,
                status=SpiderStatus.FAILED,
                error="系统正在关闭",
            )

        spider = self.registry.get_spider(spider_name)
        if spider is None:
            return SpiderResult(
                spider_name=spider_name,
                status=SpiderStatus.FAILED,
                error=f"爬虫 '{spider_name}' 不存在",
            )

        result = SpiderResult(
            spider_name=spider_name,
            status=SpiderStatus.RUNNING,
        )

        start_time = time.monotonic()
        actual_timeout = timeout or self.timeout

        # 增加活跃任务计数
        await shutdown_manager.increment_task()

        try:
            logger.info(
                "开始执行爬虫",
                spider_name=spider_name,
                trace_id=ctx.trace_id,
                active_tasks=shutdown_manager.active_task_count,
            )

            # 执行 setup 钩子
            await asyncio.wait_for(spider.setup(ctx), timeout=actual_timeout)

            # 检查关闭信号
            if shutdown_manager.should_shutdown:
                result.status = SpiderStatus.FAILED
                result.error = "收到关闭信号，任务取消"
                return result

            # 执行爬虫
            data = await asyncio.wait_for(spider.run(ctx), timeout=actual_timeout)

            # 检查关闭信号
            if shutdown_manager.should_shutdown:
                # 仍然保存已获取的数据
                result.status = SpiderStatus.SUCCESS
                result.data = data
                logger.warning(
                    "爬虫被中断但已获取部分数据",
                    spider_name=spider_name,
                    item_count=len(data),
                )
            else:
                # 执行 teardown 钩子
                await asyncio.wait_for(spider.teardown(ctx), timeout=actual_timeout)

                result.status = SpiderStatus.SUCCESS
                result.data = data

                logger.info(
                    "爬虫执行成功",
                    spider_name=spider_name,
                    item_count=len(data),
                    trace_id=ctx.trace_id,
                )

        except asyncio.TimeoutError:
            result.status = SpiderStatus.TIMEOUT
            result.error = f"爬虫执行超时（{actual_timeout}秒）"
            logger.warning(
                "爬虫执行超时",
                spider_name=spider_name,
                timeout=actual_timeout,
                trace_id=ctx.trace_id,
            )

        except asyncio.CancelledError:
            result.status = SpiderStatus.FAILED
            result.error = "任务被取消"
            logger.warning(
                "爬虫任务被取消",
                spider_name=spider_name,
                trace_id=ctx.trace_id,
            )
            raise  # 重新抛出以便上层处理

        except Exception as e:
            result.status = SpiderStatus.FAILED
            result.error = str(e)
            logger.error(
                "爬虫执行失败",
                spider_name=spider_name,
                error=str(e),
                trace_id=ctx.trace_id,
                exc_info=True,
            )

        finally:
            # 减少活跃任务计数
            await shutdown_manager.decrement_task()

            result.duration = time.monotonic() - start_time
            result.end_time = datetime.now()

            # 更新引擎统计
            self._stats.add_result(result)

            # Record metrics
            status = "success" if result.is_success else "failed"
            SpiderMetrics.record_request(
                spider=spider_name,
                status=status,
                duration=result.duration,
            )

            if result.is_success and result.item_count > 0:
                SpiderMetrics.record_items(spider_name, result.item_count)

            if result.error:
                error_type = "timeout" if "timeout" in result.error.lower() else "unknown"
                SpiderMetrics.record_error(spider_name, error_type)

        return result

    async def run_many(
        self,
        spider_names: list[str],
        ctx: SpiderContext,
        concurrent: int | None = None,
    ) -> list[SpiderResult]:
        """
        并发运行多个爬虫。

        Args:
            spider_names: 爬虫名称列表
            ctx: 爬虫上下文
            concurrent: 并发数，为 None 时使用配置值

        Returns:
            list[SpiderResult]: 执行结果列表

        Example:
            >>> results = await engine.run_many(["boss", "lagou", "zhilian"], ctx)
            >>> for result in results:
            ...     print(f"{result.spider_name}: {result.status.value}")
        """
        # 检查是否应该关闭
        if shutdown_manager.should_shutdown:
            logger.warning("系统正在关闭，跳过批量执行")
            return []

        actual_concurrent = concurrent or self.max_concurrent
        semaphore = asyncio.Semaphore(actual_concurrent)

        stats = EngineStats()
        all_results: list[SpiderResult] = []
        pending_tasks: set[asyncio.Task] = set()

        async def run_with_semaphore(spider_name: str) -> SpiderResult:
            async with semaphore:
                # 检查关闭信号
                if shutdown_manager.should_shutdown:
                    return SpiderResult(
                        spider_name=spider_name,
                        status=SpiderStatus.FAILED,
                        error="系统正在关闭",
                    )
                result = await self.run_one(spider_name, ctx)
                stats.add_result(result)
                return result

        logger.info(
            "开始批量执行爬虫",
            spider_count=len(spider_names),
            concurrent=actual_concurrent,
            trace_id=ctx.trace_id,
        )

        # Set active spiders gauge
        SpiderMetrics.set_active_spiders(len(spider_names))

        start_time = time.monotonic()

        try:
            # 创建任务
            for name in spider_names:
                if shutdown_manager.should_shutdown:
                    break
                task = asyncio.create_task(run_with_semaphore(name))
                pending_tasks.add(task)
                task.add_done_callback(pending_tasks.discard)

            # 等待所有任务完成或关闭信号
            if pending_tasks:
                shutdown_task = asyncio.create_task(shutdown_manager.wait_for_shutdown())

                done, pending = await asyncio.wait(
                    pending_tasks | {shutdown_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # 如果收到关闭信号，取消剩余任务
                if shutdown_task in done:
                    logger.warning(
                        "收到关闭信号，取消剩余任务",
                        pending_tasks=len(pending_tasks),
                    )
                    for task in pending_tasks:
                        if task is not shutdown_task:
                            task.cancel()

                    # 等待被取消的任务完成
                    if pending_tasks - {shutdown_task}:
                        await asyncio.gather(
                            *(pending_tasks - {shutdown_task}),
                            return_exceptions=True,
                        )

                # 收集结果
                for task in pending_tasks:
                    if task is not shutdown_task:
                        try:
                            result = task.result()
                            all_results.append(result)
                        except (asyncio.CancelledError, Exception) as e:
                            # 找到对应的爬虫名称
                            idx = len(all_results)
                            if idx < len(spider_names):
                                all_results.append(SpiderResult(
                                    spider_name=spider_names[idx],
                                    status=SpiderStatus.FAILED,
                                    error=f"任务被取消: {str(e)}",
                                ))
            else:
                all_results = await asyncio.gather(*pending_tasks, return_exceptions=True)

        except asyncio.CancelledError:
            logger.warning("批量执行被取消")
            # 取消所有待处理任务
            for task in pending_tasks:
                task.cancel()
            raise

        # 处理可能的异常结果
        processed_results: list[SpiderResult] = []
        for i, result in enumerate(all_results):
            if isinstance(result, Exception):
                processed_results.append(SpiderResult(
                    spider_name=spider_names[i] if i < len(spider_names) else f"unknown_{i}",
                    status=SpiderStatus.FAILED,
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        total_duration = time.monotonic() - start_time

        logger.info(
            "批量执行完成",
            total_spiders=stats.total_spiders,
            success_count=stats.success_count,
            failed_count=stats.failed_count,
            total_items=stats.total_items,
            total_duration=total_duration,
            trace_id=ctx.trace_id,
            was_interrupted=shutdown_manager.should_shutdown,
        )

        # Reset active spiders gauge
        SpiderMetrics.set_active_spiders(0)

        return processed_results

    async def run_all(
        self,
        ctx: SpiderContext,
        concurrent: int | None = None,
    ) -> list[SpiderResult]:
        """
        运行所有已注册的爬虫。

        Args:
            ctx: 爬虫上下文
            concurrent: 并发数

        Returns:
            list[SpiderResult]: 执行结果列表

        Example:
            >>> results = await engine.run_all(ctx)
            >>> print(f"总共爬取 {sum(r.item_count for r in results)} 条数据")
        """
        spider_names = self.registry.list_spiders()
        return await self.run_many(spider_names, ctx, concurrent)
