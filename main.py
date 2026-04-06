#!/usr/bin/env python3
"""CLI entry point for job-spider."""

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from config.logging import configure_logging, get_logger
from config.settings import get_settings
from job_spider.core.engine import SpiderEngine
from job_spider.core.shutdown import shutdown_manager
from job_spider.spiders.base import SpiderContext, SpiderRegistry
from job_spider.storage.backup import DatabaseBackup
import job_spider.spiders.zhilian
import job_spider.spiders.zhilian_browser
import job_spider.spiders.job51
import job_spider.spiders.mock

console = Console()
logger = get_logger("cli")


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool):
    """Job Spider - 招聘数据爬虫系统."""
    settings = get_settings()
    if debug:
        settings.debug = True

    configure_logging()


@cli.command()
def list_spiders():
    """列出所有可用的爬虫."""
    table = Table(title="可用爬虫")
    table.add_column("名称", style="cyan")
    table.add_column("版本", style="green")
    table.add_column("状态", style="yellow")

    for name in SpiderRegistry.list_spiders():
        spider_cls = SpiderRegistry.get_spider(name)
        version = getattr(spider_cls, "version", "unknown") if spider_cls else "unknown"
        table.add_row(name, version, "可用")

    if not SpiderRegistry.list_spiders():
        console.print("[yellow]没有注册的爬虫[/yellow]")
    else:
        console.print(table)


@cli.command()
@click.argument("spider_name")
@click.option("--keyword", "-k", required=True, help="搜索关键词")
@click.option("--city", "-c", required=True, help="城市")
@click.option("--limit", "-l", default=100, help="爬取数量限制")
@click.option("--concurrency", default=3, help="并发数")
@click.option("--save", "-s", is_flag=True, default=True, help="保存到数据库")
@click.option("--login", is_flag=True, help="登录模式（打开浏览器手动登录）")
@click.option("--shutdown-timeout", default=30.0, help="优雅关闭超时时间（秒）")
def crawl(spider_name: str, keyword: str, city: str, limit: int, concurrency: int, save: bool, login: bool, shutdown_timeout: float):
    """执行爬虫任务.

    示例:
        python main.py crawl zhilian -k "Python开发" -c "深圳" -l 100
        python main.py crawl zhilian-browser -k "Python" -c "北京" --login  # 首次登录
        python main.py crawl zhilian-browser -k "Python" -c "北京"         # 使用已保存的登录状态
    """
    settings = get_settings()

    # Check spider exists
    if spider_name not in SpiderRegistry.list_spiders():
        console.print(f"[red]错误: 未知的爬虫 '{spider_name}'[/red]")
        console.print(f"可用爬虫: {', '.join(SpiderRegistry.list_spiders()) or '无'}")
        return

    console.print(f"[green]开始爬取 {spider_name}...[/green]")
    console.print(f"关键词: {keyword}, 城市: {city}, 数量: {limit}")

    # 设置关闭超时
    shutdown_manager.timeout = shutdown_timeout

    # 创建上下文
    ctx = SpiderContext(
        keyword=keyword,
        city=city,
        location=city,
        limit=limit,
        extra={"login": login},
    )

    # 创建引擎（使用传入的并发数）
    settings.spider.max_concurrent = concurrency
    engine = SpiderEngine(config=settings)

    try:
        result = asyncio.run(_run_crawl_with_shutdown(engine, spider_name, ctx))

        # Display results
        table = Table(title="爬取结果")
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="green")

        table.add_row("爬虫", result.spider_name)
        table.add_row("状态", result.status.value)
        table.add_row("数量", str(result.item_count))
        table.add_row("耗时", f"{result.duration:.2f}s")

        if result.error:
            table.add_row("错误", result.error)

        console.print(table)

        if result.error:
            console.print(f"\n[yellow]错误信息: {result.error}[/yellow]")

        # 保存数据到数据库
        if save and result.is_success and result.item_count > 0:
            saved_count = asyncio.run(_save_to_database(result.data, spider_name))
            console.print(f"[green]已保存 {saved_count} 条数据到数据库[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]收到中断信号，正在关闭...[/yellow]")
    except Exception as e:
        console.print(f"[red]爬取失败: {e}[/red]")
        logger.exception("crawl_failed", spider=spider_name)


async def _run_crawl_with_shutdown(engine: SpiderEngine, spider_name: str, ctx: SpiderContext):
    """运行爬虫并支持优雅关闭。"""
    # 设置信号处理器
    shutdown_manager.setup_signal_handlers()

    # 注册引擎关闭钩子
    @shutdown_manager.register_hook
    async def cleanup_engine():
        stats = engine.get_stats()
        logger.info(
            "引擎清理中",
            active_tasks=stats.active_tasks,
            total_spiders=stats.total_spiders,
        )
        await engine.cleanup()

    try:
        result = await engine.run_one(spider_name, ctx)
        return result
    except asyncio.CancelledError:
        logger.warning("爬虫任务被取消")
        from job_spider.core.engine import SpiderResult, SpiderStatus
        return SpiderResult(
            spider_name=spider_name,
            status=SpiderStatus.FAILED,
            error="任务被取消（优雅关闭）",
        )
    finally:
        if shutdown_manager.should_shutdown:
            await shutdown_manager.shutdown()


async def _save_to_database(jobs: list[dict], source: str) -> int:
    """保存数据到数据库"""
    from job_spider.storage.database import Database
    from job_spider.storage.models import JobCreate
    from job_spider.storage.repository import JobRepository
    from decimal import Decimal

    settings = get_settings()
    db = Database(f"sqlite+aiosqlite:///{settings.database.sqlite_path}")

    async with db.get_session_async() as session:
        repo = JobRepository(session)
        saved = 0

        for job in jobs:
            try:
                # 转换薪资数据
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                salary_avg = None
                if salary_min and salary_max:
                    salary_avg = Decimal(str((salary_min + salary_max) / 2))

                job_data = JobCreate(
                    job_id=job.get("job_id") or f"{source}_{saved}",
                    source=job.get("source") or source,
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    salary_min=Decimal(str(salary_min)) if salary_min else None,
                    salary_max=Decimal(str(salary_max)) if salary_max else None,
                    salary_avg=salary_avg,
                    city=job.get("city") or job.get("location"),
                    experience=job.get("experience"),
                    education=job.get("education"),
                    company_size=job.get("company_size"),
                    company_industry=job.get("company_industry"),
                    url=job.get("url"),
                    status="active",
                )

                await repo.save_async(job_data)
                saved += 1

            except Exception as e:
                logger.warning(f"Failed to save job: {e}")
                continue

        await session.commit()
        return saved


@cli.command()
@click.option("--spider", "-s", default=None, help="爬虫名称过滤")
def stats(spider: str | None):
    """查看爬取统计信息."""
    settings = get_settings()
    db_path = Path(settings.database.sqlite_path)

    if not db_path.exists():
        console.print("[yellow]数据库不存在，请先执行爬取任务[/yellow]")
        return

    from sqlalchemy import create_engine, func, select
    from job_spider.storage.models import JobProcessed

    # 创建同步引擎查询
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        # 总职位数
        total_result = conn.execute(select(func.count()).select_from(JobProcessed))
        total_count = total_result.scalar() or 0

        # 按城市分布 TOP 10
        city_result = conn.execute(
            select(JobProcessed.city, func.count().label("count"))
            .where(JobProcessed.city.isnot(None))
            .group_by(JobProcessed.city)
            .order_by(func.count().desc())
            .limit(10)
        )
        city_stats = city_result.fetchall()

        # 按数据来源分布
        source_result = conn.execute(
            select(JobProcessed.source, func.count().label("count"))
            .group_by(JobProcessed.source)
            .order_by(func.count().desc())
        )
        source_stats = source_result.fetchall()

    # 显示总职位数
    console.print(f"\n[bold cyan]总职位数:[/bold cyan] {total_count}\n")

    # 显示城市分布
    if city_stats:
        city_table = Table(title="城市分布 TOP 10")
        city_table.add_column("城市", style="cyan")
        city_table.add_column("数量", style="green")
        city_table.add_column("占比", style="yellow")

        for city, count in city_stats:
            ratio = f"{count / total_count * 100:.1f}%" if total_count > 0 else "0%"
            city_table.add_row(city or "未知", str(count), ratio)

        console.print(city_table)
        console.print()

    # 显示数据来源分布
    if source_stats:
        source_table = Table(title="数据来源分布")
        source_table.add_column("来源", style="cyan")
        source_table.add_column("数量", style="green")
        source_table.add_column("占比", style="yellow")

        for source, count in source_stats:
            ratio = f"{count / total_count * 100:.1f}%" if total_count > 0 else "0%"
            source_table.add_row(source or "未知", str(count), ratio)

        console.print(source_table)


@cli.command()
@click.option("--format", "-f", type=click.Choice(["csv", "excel"]), default="csv", help="导出格式")
@click.option("--output", "-o", default="output/jobs", help="输出文件路径(不含扩展名)")
@click.option("--city", "-c", default=None, help="按城市过滤")
@click.option("--source", "-s", default=None, help="按数据来源过滤")
@click.option("--limit", "-l", default=None, type=int, help="导出数量限制")
def export(format: str, output: str, city: str | None, source: str | None, limit: int | None):
    """导出数据."""
    settings = get_settings()
    db_path = Path(settings.database.sqlite_path)

    if not db_path.exists():
        console.print("[yellow]数据库不存在，请先执行爬取任务[/yellow]")
        return

    from sqlalchemy import create_engine, select
    from job_spider.storage.models import JobProcessed
    from job_spider.storage.exporter import Exporter

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建同步引擎查询
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        # 构建查询
        query = select(JobProcessed)

        # 应用过滤条件
        if city:
            query = query.where(JobProcessed.city == city)
        if source:
            query = query.where(JobProcessed.source == source)
        if limit:
            query = query.limit(limit)

        result = conn.execute(query)
        jobs = result.fetchall()

    if not jobs:
        console.print("[yellow]没有找到符合条件的数据[/yellow]")
        return

    # 转换为字典列表
    job_list = []
    for job in jobs:
        job_dict = {
            "job_id": job.job_id,
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_avg": job.salary_avg,
            "city": job.city,
            "district": job.district,
            "address": job.address,
            "experience": job.experience,
            "education": job.education,
            "skills": job.skills,
            "company_size": job.company_size,
            "company_industry": job.company_industry,
            "company_stage": job.company_stage,
            "url": job.url,
            "publish_time": job.publish_time,
            "crawl_time": job.crawl_time,
            "status": job.status,
        }
        job_list.append(job_dict)

    # 导出数据
    exporter = Exporter()

    if format == "csv":
        file_path = f"{output_path}.csv"
        exporter.to_csv(job_list, output_path=file_path)
        console.print(f"[green]已导出 {len(job_list)} 条数据到: {file_path}[/green]")
    else:
        file_path = f"{output_path}.xlsx"
        exporter.to_excel(job_list, output_path=file_path)
        console.print(f"[green]已导出 {len(job_list)} 条数据到: {file_path}[/green]")


@cli.command()
def init():
    """初始化项目."""
    settings = get_settings()

    # Create directories
    directories = [
        Path(settings.database.sqlite_path).parent,
        settings.storage.output_dir,
        settings.storage.logs_dir,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        console.print(f"创建目录: {directory}")

    # Initialize database
    from job_spider.storage.database import Database

    db_url = f"sqlite:///{settings.database.sqlite_path}"
    db = Database(db_url)
    asyncio.run(db.init_db_async())
    console.print("[green]数据库初始化完成[/green]")

    console.print("\n[green]项目初始化完成！[/green]")
    console.print("\n使用示例:")
    console.print("  python main.py crawl zhilian -k 'Python开发' -c '深圳'")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Metrics server host")
@click.option("--port", "-p", default=8000, help="Metrics server port")
def metrics_server(host: str, port: int):
    """启动 Prometheus 指标服务器.

    提供 Prometheus 格式的指标导出端点:
    - /metrics - Prometheus 指标
    - /health - 健康检查

    示例:
        python main.py metrics-server
        python main.py metrics-server --port 9090
    """
    from job_spider.observability.metrics_server import run_metrics_server

    console.print(f"[green]启动指标服务器: http://{host}:{port}/metrics[/green]")
    console.print("[yellow]按 Ctrl+C 停止服务器[/yellow]")

    try:
        run_metrics_server(host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]服务器已停止[/yellow]")


@cli.command()
@click.option("--port", "-p", default=8080, help="Health server port")
@click.option("--host", "-h", default="0.0.0.0", help="Bind address")
@click.option("--daemon", "-d", is_flag=True, help="Run as background service")
def health(port: int, host: str, daemon: bool):
    """启动健康检查服务.

    提供用于 K8s/Docker 健康探针的 HTTP 端点:
    - /health - 存活探针（进程存活）
    - /ready - 就绪探针（数据库连接、配置加载）

    示例:
        python main.py health --port 8080
        python main.py health --daemon  # 后台运行
    """
    from job_spider.health.server import run_health_server

    console.print(f"[green]启动健康检查服务[/green]")
    console.print(f"地址: http://{host}:{port}")
    console.print(f"端点:")
    console.print(f"  - /health (存活探针)")
    console.print(f"  - /ready (就绪探针)")
    console.print()

    if daemon:
        console.print("[yellow]后台模式运行，按 Ctrl+C 停止[/yellow]")

    try:
        asyncio.run(run_health_server(port=port, host=host, daemon=daemon))
    except KeyboardInterrupt:
        console.print("\n[yellow]健康检查服务已停止[/yellow]")


# ==================== 备份命令组 ====================

@click.group()
def backup():
    """数据库备份管理.

    提供数据库的备份、恢复、列表和清理功能。

    示例:
        python main.py backup create              # 创建备份
        python main.py backup list                # 列出所有备份
        python main.py backup restore <name>      # 恢复指定备份
        python main.py backup cleanup             # 清理旧备份
        python main.py backup stats               # 查看备份统计
    """
    pass


@backup.command()
@click.option("--name", "-n", default=None, help="自定义备份名称")
@click.option("--compress/--no-compress", default=None, help="是否压缩备份（默认使用配置）")
def create(name: str | None, compress: bool | None):
    """创建数据库备份.

    使用 SQLite 备份 API 确保数据一致性。

    示例:
        python main.py backup create
        python main.py backup create --name manual_backup
        python main.py backup create --no-compress
    """
    settings = get_settings()

    # 检查数据库是否存在
    db_path = Path(settings.database.sqlite_path)
    if not db_path.exists():
        console.print(f"[red]错误: 数据库文件不存在: {db_path}[/red]")
        console.print("[yellow]请先执行爬取任务或初始化数据库[/yellow]")
        return

    # 创建备份管理器
    use_compress = compress if compress is not None else settings.backup.compress
    backup_manager = DatabaseBackup(
        db_path=db_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=use_compress,
    )

    console.print(f"[cyan]正在创建备份...[/cyan]")
    console.print(f"数据库: {db_path}")
    console.print(f"备份目录: {settings.backup.backup_dir}")
    console.print(f"压缩: {'是' if use_compress else '否'}")

    # 创建备份
    result = backup_manager.create_backup(custom_name=name)

    if result.success:
        console.print(f"\n[green]{result.message}[/green]")
        console.print(f"备份文件: {result.backup_name}")
        if result.size:
            size_str = f"{result.size / 1024 / 1024:.2f} MB" if result.size > 1024 * 1024 else f"{result.size / 1024:.2f} KB"
            console.print(f"文件大小: {size_str}")
    else:
        console.print(f"\n[red]{result.message}[/red]")


@backup.command("list")
@click.option("--all", "-a", "show_all", is_flag=True, help="显示所有备份（包括无效的）")
def list_backups(show_all: bool):
    """列出所有备份.

    显示备份文件的名称、大小、创建时间和状态。

    示例:
        python main.py backup list
        python main.py backup list --all
    """
    settings = get_settings()

    # 检查备份目录是否存在
    backup_dir = Path(settings.backup.backup_dir)
    if not backup_dir.exists():
        console.print(f"[yellow]备份目录不存在: {backup_dir}[/yellow]")
        console.print("[yellow]还没有创建过备份[/yellow]")
        return

    # 创建备份管理器
    backup_manager = DatabaseBackup(
        db_path=settings.database.sqlite_path,
        backup_dir=backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    # 获取备份列表
    backups = backup_manager.list_backups()

    if not backups:
        console.print("[yellow]没有找到备份文件[/yellow]")
        return

    # 过滤无效备份
    if not show_all:
        valid_backups = [b for b in backups if b.status.value == "valid"]
        if len(valid_backups) < len(backups):
            console.print(f"[yellow]注: 有 {len(backups) - len(valid_backups)} 个无效/损坏的备份未显示，使用 --all 查看[/yellow]\n")
        backups = valid_backups

    # 创建表格
    table = Table(title=f"备份列表 (共 {len(backups)} 个)")
    table.add_column("序号", style="dim", width=4)
    table.add_column("名称", style="cyan")
    table.add_column("大小", style="green")
    table.add_column("创建时间", style="yellow")
    table.add_column("压缩", style="blue")
    table.add_column("状态", style="magenta")

    for i, backup_info in enumerate(backups, 1):
        status_style = {
            "valid": "green",
            "invalid": "yellow",
            "corrupted": "red",
        }.get(backup_info.status.value, "white")

        table.add_row(
            str(i),
            backup_info.name,
            backup_info.size_human,
            backup_info.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "是" if backup_info.compressed else "否",
            f"[{status_style}]{backup_info.status.value}[/{status_style}]",
        )

    console.print(table)


@backup.command()
@click.argument("backup_name")
def restore(backup_name: str):
    """从备份恢复数据库.

    警告: 恢复操作会覆盖当前数据库文件。

    示例:
        python main.py backup restore jobs_backup_20240101_120000.db.gz
    """
    settings = get_settings()

    # 检查数据库路径
    db_path = Path(settings.database.sqlite_path)

    # 创建备份管理器
    backup_manager = DatabaseBackup(
        db_path=db_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    # 确认恢复操作
    console.print(f"[yellow]警告: 此操作将覆盖当前数据库文件！[/yellow]")
    console.print(f"备份文件: {backup_name}")
    console.print(f"目标位置: {db_path}")

    if not click.confirm("\n确定要继续吗？", default=False):
        console.print("[yellow]已取消恢复操作[/yellow]")
        return

    # 执行恢复
    console.print("\n[cyan]正在恢复数据库...[/cyan]")
    result = backup_manager.restore_backup(backup_name)

    if result.success:
        console.print(f"\n[green]{result.message}[/green]")
        console.print(f"已从备份恢复: {result.restored_from}")
    else:
        console.print(f"\n[red]{result.message}[/red]")


@backup.command()
@click.option("--keep", "-k", default=None, type=int, help="保留的备份数量（默认使用配置）")
@click.option("--force", "-f", is_flag=True, help="强制删除，不提示确认")
def cleanup(keep: int | None, force: bool):
    """清理旧备份.

    保留最近 N 个备份，删除其余的旧备份。

    示例:
        python main.py backup cleanup
        python main.py backup cleanup --keep 5
        python main.py backup cleanup --force
    """
    settings = get_settings()

    # 创建备份管理器
    backup_manager = DatabaseBackup(
        db_path=settings.database.sqlite_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    keep_count = keep if keep is not None else settings.backup.max_backups

    # 获取当前备份列表
    backups = backup_manager.list_backups()
    valid_backups = [b for b in backups if b.status.value == "valid"]

    if len(valid_backups) <= keep_count:
        console.print(f"[green]当前有 {len(valid_backups)} 个有效备份，无需清理[/green]")
        console.print(f"保留数量设置: {keep_count}")
        return

    to_delete_count = len(valid_backups) - keep_count
    console.print(f"[cyan]将删除 {to_delete_count} 个旧备份，保留最近 {keep_count} 个[/cyan]")

    if not force:
        if not click.confirm("确定要继续吗？", default=False):
            console.print("[yellow]已取消清理操作[/yellow]")
            return

    # 执行清理
    deleted = backup_manager.cleanup_old_backups(keep_count)

    if deleted:
        console.print(f"\n[green]已删除 {len(deleted)} 个备份:[/green]")
        for name in deleted:
            console.print(f"  - {name}")
    else:
        console.print("\n[yellow]没有需要清理的备份[/yellow]")


@backup.command()
def stats():
    """查看备份统计信息.

    显示备份数量、总大小、状态分布等统计信息。

    示例:
        python main.py backup stats
    """
    settings = get_settings()

    # 创建备份管理器
    backup_manager = DatabaseBackup(
        db_path=settings.database.sqlite_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    # 获取统计信息
    stats_info = backup_manager.get_backup_stats()

    # 创建表格
    table = Table(title="备份统计")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")

    table.add_row("总备份数", str(stats_info["total_count"]))
    table.add_row("有效备份", str(stats_info["valid_count"]))
    table.add_row("无效备份", str(stats_info["invalid_count"]))
    table.add_row("损坏备份", str(stats_info["corrupted_count"]))
    table.add_row("总大小", stats_info["total_size_human"])
    table.add_row("备份目录", stats_info["backup_dir"])
    table.add_row("最大保留数", str(stats_info["max_backups"]))

    console.print(table)


@backup.command()
@click.argument("backup_name")
def verify(backup_name: str):
    """验证备份文件完整性.

    检查备份文件是否损坏，是否可以正常恢复。

    示例:
        python main.py backup verify jobs_backup_20240101_120000.db.gz
    """
    settings = get_settings()

    # 创建备份管理器
    backup_manager = DatabaseBackup(
        db_path=settings.database.sqlite_path,
        backup_dir=settings.backup.backup_dir,
        max_backups=settings.backup.max_backups,
        compress=settings.backup.compress,
    )

    console.print(f"[cyan]正在验证备份: {backup_name}[/cyan]")

    # 验证备份
    status = backup_manager.verify_backup(backup_name)

    if status.value == "valid":
        console.print(f"\n[green]备份文件有效，可以正常恢复[/green]")
    elif status.value == "invalid":
        console.print(f"\n[yellow]备份文件存在完整性问题，建议重新创建备份[/yellow]")
    else:
        console.print(f"\n[red]备份文件已损坏，无法恢复[/red]")

    # 显示详细信息
    backup_info = backup_manager.get_backup_info(backup_name)
    if backup_info:
        console.print(f"\n文件大小: {backup_info.size_human}")
        console.print(f"创建时间: {backup_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        console.print(f"是否压缩: {'是' if backup_info.compressed else '否'}")


# 将备份命令组添加到主命令组
cli.add_command(backup)


if __name__ == "__main__":
    cli()
