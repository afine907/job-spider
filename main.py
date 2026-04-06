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
from job_spider.spiders.base import SpiderContext, SpiderRegistry
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
def crawl(spider_name: str, keyword: str, city: str, limit: int, concurrency: int, save: bool, login: bool):
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
        result = asyncio.run(engine.run_one(spider_name, ctx))

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

    except Exception as e:
        console.print(f"[red]爬取失败: {e}[/red]")
        logger.exception("crawl_failed", spider=spider_name)


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
        Path("output"),
        Path("logs"),
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


if __name__ == "__main__":
    cli()
