"""
测试爬虫 - 使用公开的招聘 API 进行测试

使用 GitHub Jobs API (已弃用) 或模拟数据验证框架功能。
"""

from __future__ import annotations

import logging
import random
from datetime import datetime

from .base import (
    BaseSpider,
    CrawlResult,
    JobItem,
    SpiderContext,
    SpiderRegistry,
)

logger = logging.getLogger(__name__)


@SpiderRegistry.register
class MockSpider(BaseSpider):
    """
    模拟爬虫 - 用于测试框架功能

    生成模拟的职位数据，验证整个数据处理管道是否正常工作。
    """

    name = "mock"
    version = "1.0.0"
    base_url = "https://example.com"

    # 模拟数据模板
    COMPANIES = [
        "阿里巴巴", "腾讯", "百度", "字节跳动", "美团",
        "京东", "拼多多", "网易", "小米", "华为",
        "滴滴出行", "快手", "B站", "携程", "蚂蚁集团",
    ]

    TITLES = [
        "Python开发工程师", "高级Python工程师", "Python后端开发",
        "Python全栈工程师", "Python数据工程师", "Python架构师",
        "后端开发工程师", "全栈开发工程师", "数据开发工程师",
        "算法工程师", "机器学习工程师", "AI工程师",
    ]

    LOCATIONS = [
        "北京", "上海", "广州", "深圳", "杭州",
        "成都", "武汉", "南京", "西安", "重庆",
    ]

    EDUCATIONS = ["本科", "硕士", "博士", "大专", "不限"]
    EXPERIENCES = ["1-3年", "3-5年", "5-10年", "应届生", "不限"]

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """
        生成模拟职位数据

        Args:
            ctx: 爬虫上下文

        Returns:
            CrawlResult: 包含模拟数据的爬取结果
        """
        items: list[JobItem] = []
        count = min(ctx.limit, 100)  # 最多生成100条

        logger.info(f"Generating {count} mock job items for keyword: {ctx.keyword}")

        for i in range(count):
            # 生成随机薪资
            salary_min = random.randint(10, 30) * 1000
            salary_max = salary_min + random.randint(5, 20) * 1000

            # 创建职位项
            item = JobItem(
                title=self._generate_title(ctx.keyword),
                company=random.choice(self.COMPANIES),
                url=f"https://example.com/jobs/{i + 1}",
                source=self.name,
                salary_raw=f"{salary_min // 1000}K-{salary_max // 1000}K",
                salary_min=salary_min,
                salary_max=salary_max,
                location=ctx.location or random.choice(self.LOCATIONS),
                experience=random.choice(self.EXPERIENCES),
                education=random.choice(self.EDUCATIONS),
                job_id=f"mock_{i + 1}",
                published_at=datetime.now(),
                company_size=random.choice(["100-499人", "500-999人", "1000-9999人", "10000人以上"]),
                company_industry=random.choice(["互联网", "金融", "电商", "教育", "游戏"]),
            )

            items.append(item)

        return CrawlResult(
            success=True,
            items=items,
            total_count=count,
            page=1,
            has_more=False,
            metadata={
                "source": self.name,
                "keyword": ctx.keyword,
                "mock": True,
            },
        )

    def _generate_title(self, keyword: str) -> str:
        """根据关键词生成职位标题"""
        if keyword:
            return f"{keyword} {random.choice(self.TITLES)}"
        return random.choice(self.TITLES)


@SpiderRegistry.register
class RemoteOKSpider(BaseSpider):
    """
    RemoteOK 爬虫 - 使用公开的远程工作 API

    API 文档: https://remoteok.com/api
    这是一个公开的 API，无需认证。
    """

    name = "remoteok"
    version = "1.0.0"
    base_url = "https://remoteok.com"

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """
        从 RemoteOK API 获取远程工作职位

        Args:
            ctx: 爬虫上下文

        Returns:
            CrawlResult: 爬取结果
        """
        import httpx

        items: list[JobItem] = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    "https://remoteok.com/api",
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()

                data = response.json()

                # 跳过第一个元素（它是 API 元信息）
                jobs = data[1:] if len(data) > 1 else data

                # 过滤关键词
                if ctx.keyword:
                    keyword_lower = ctx.keyword.lower()
                    jobs = [
                        job for job in jobs
                        if keyword_lower in job.get("title", "").lower()
                        or keyword_lower in job.get("description", "").lower()
                    ]

                # 限制数量
                jobs = jobs[:ctx.limit]

                for job in jobs:
                    # 解析薪资
                    salary_min = job.get("salary_min")
                    salary_max = job.get("salary_max")

                    # 转换为月薪（如果是年薪）
                    if salary_min and salary_min > 100000:
                        salary_min = salary_min // 12
                    if salary_max and salary_max > 100000:
                        salary_max = salary_max // 12

                    item = JobItem(
                        title=job.get("title", "Unknown"),
                        company=job.get("company", "Unknown"),
                        url=f"https://remoteok.com/remote-jobs/{job.get('id', '')}",
                        source=self.name,
                        salary_raw=job.get("salary", "") or "",
                        salary_min=salary_min,
                        salary_max=salary_max,
                        location=job.get("location", "Remote"),
                        experience="",
                        education="",
                        job_id=str(job.get("id", "")),
                        published_at=datetime.fromtimestamp(job.get("epoch", 0)) if job.get("epoch") else None,
                        company_industry=job.get("category", ""),
                        raw_data=job,
                    )

                    items.append(item)

                logger.info(f"Fetched {len(items)} jobs from RemoteOK API")

        except Exception as e:
            logger.error(f"Failed to fetch from RemoteOK: {e}")
            return CrawlResult(
                success=False,
                items=[],
                error=str(e),
            )

        return CrawlResult(
            success=True,
            items=items,
            total_count=len(items),
            page=1,
            has_more=False,
            metadata={"source": self.name, "keyword": ctx.keyword},
        )
