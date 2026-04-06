"""
爬虫基类模块

提供爬虫的抽象基类、数据模型和注册中心。
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class SpiderStatus(Enum):
    """爬虫状态枚举"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SpiderContext:
    """
    爬虫上下文

    包含爬虫执行过程中需要的所有上下文信息。
    """

    # 搜索参数
    keyword: str = ""
    location: str = ""
    city: str = ""  # 城市名称
    page: int = 1
    page_size: int = 20
    limit: int = 100  # 爬取数量限制

    # 追踪和配置
    trace_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    config: Any = None  # 配置对象

    # 请求配置
    request_delay: tuple[float, float] = (1.0, 3.0)
    timeout: float = 30.0
    max_retries: int = 3

    # 代理配置
    proxy: Optional[str] = None

    # 自定义请求头
    headers: dict[str, str] = field(default_factory=dict)

    # 扩展数据
    extra: dict[str, Any] = field(default_factory=dict)

    def get_delay(self) -> float:
        """获取随机延迟时间"""
        return random.uniform(self.request_delay[0], self.request_delay[1])


@dataclass
class JobItem:
    """
    职位数据模型

    包含职位的基本信息。
    """

    # 基本信息
    title: str
    company: str
    url: str
    source: str  # 来源网站

    # 薪资信息
    salary_raw: str = ""
    salary_min: Optional[int] = None  # 最低薪资（元/月）
    salary_max: Optional[int] = None  # 最高薪资（元/月）

    # 职位详情
    location: str = ""
    experience: str = ""
    education: str = ""
    job_type: str = ""  # 全职/兼职等

    # 公司信息
    company_size: str = ""
    company_industry: str = ""

    # 元数据
    job_id: str = ""
    published_at: Optional[datetime] = None
    crawled_at: datetime = field(default_factory=datetime.now)

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "source": self.source,
            "salary_raw": self.salary_raw,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "location": self.location,
            "experience": self.experience,
            "education": self.education,
            "job_type": self.job_type,
            "company_size": self.company_size,
            "company_industry": self.company_industry,
            "job_id": self.job_id,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "crawled_at": self.crawled_at.isoformat(),
        }


@dataclass
class CrawlResult:
    """
    爬取结果

    包含单次爬取的结果数据。
    """

    success: bool
    items: list[JobItem] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    has_more: bool = False
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return self.success


class SpiderRegistry:
    """
    爬虫注册中心

    管理所有已注册的爬虫实例。
    """

    _instance: Optional[SpiderRegistry] = None
    _spiders: dict[str, type[BaseSpider]] = {}

    def __new__(cls) -> SpiderRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, spider_class: type[BaseSpider]) -> type[BaseSpider]:
        """
        注册爬虫类

        用作装饰器：
        @SpiderRegistry.register
        class MySpider(BaseSpider):
            ...
        """
        instance = spider_class()
        cls._spiders[instance.name] = spider_class
        logger.info(f"Registered spider: {instance.name}")
        return spider_class

    @classmethod
    def get_spider(cls, name: str) -> Optional[BaseSpider]:
        """获取爬虫实例"""
        spider_class = cls._spiders.get(name)
        if spider_class:
            return spider_class()
        return None

    @classmethod
    def list_spiders(cls) -> list[str]:
        """列出所有已注册的爬虫名称"""
        return list(cls._spiders.keys())


class BaseSpider(ABC):
    """
    爬虫抽象基类

    所有爬虫必须继承此类并实现抽象方法。

    Attributes:
        name: 爬虫唯一标识名称
        version: 爬虫版本号
        base_url: 目标网站基础URL

    Example:
        class MySpider(BaseSpider):
            name = "my_spider"
            version = "1.0.0"
            base_url = "https://example.com"

            async def search(self, ctx: SpiderContext) -> CrawlResult:
                # 实现搜索逻辑
                ...
    """

    name: str = "base_spider"
    version: str = "1.0.0"
    base_url: str = ""

    def __init__(self) -> None:
        self._status = SpiderStatus.IDLE
        self._client: Optional[httpx.AsyncClient] = None
        self._context: Optional[SpiderContext] = None

    @property
    def status(self) -> SpiderStatus:
        """获取爬虫当前状态"""
        return self._status

    @abstractmethod
    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """
        搜索职位列表（抽象方法）

        子类必须实现此方法。

        Args:
            ctx: 爬虫上下文，包含搜索参数和配置

        Returns:
            CrawlResult: 爬取结果
        """
        pass

    async def get_detail(self, url: str, ctx: SpiderContext) -> Optional[JobItem]:
        """
        获取职位详情（可选实现）

        子类可以覆盖此方法以获取更详细的职位信息。

        Args:
            url: 职位详情页URL
            ctx: 爬虫上下文

        Returns:
            JobItem: 职位详情，如果获取失败返回None
        """
        return None

    async def setup(self, ctx: SpiderContext) -> None:
        """
        爬虫初始化钩子

        在 run 之前调用，用于准备资源。

        Args:
            ctx: 爬虫上下文
        """
        pass

    async def run(self, ctx: SpiderContext) -> list[dict[str, Any]]:
        """
        执行爬取并返回数据列表

        这是引擎调用的主要方法。

        Args:
            ctx: 爬虫上下文

        Returns:
            list[dict[str, Any]]: 爬取的数据列表
        """
        result = await self.search(ctx)
        return [item.to_dict() for item in result.items]

    async def teardown(self, ctx: SpiderContext) -> None:
        """
        爬虫清理钩子

        在 run 之后调用，用于清理资源。

        Args:
            ctx: 爬虫上下文
        """
        await self.close()

    async def execute(self, ctx: SpiderContext) -> CrawlResult:
        """
        执行爬取任务（模板方法）

        包含完整的执行流程：前置检查 -> 执行爬取 -> 后置处理

        Args:
            ctx: 爬虫上下文

        Returns:
            CrawlResult: 爬取结果
        """
        self._context = ctx

        try:
            # 前置检查
            await self._preflight_check(ctx)

            # 执行爬取
            self._status = SpiderStatus.RUNNING
            logger.info(f"Spider [{self.name}] starting search with keyword: {ctx.keyword}")

            result = await self.search(ctx)

            # 后置处理
            await self._post_process(result, ctx)

            self._status = SpiderStatus.IDLE
            logger.info(f"Spider [{self.name}] completed, got {len(result.items)} items")

            return result

        except Exception as e:
            self._status = SpiderStatus.ERROR
            logger.error(f"Spider [{self.name}] failed: {e}")
            return CrawlResult(success=False, error=str(e))

    async def _preflight_check(self, ctx: SpiderContext) -> None:
        """
        前置检查

        检查爬虫是否可以正常工作。

        Args:
            ctx: 爬虫上下文
        """
        logger.debug(f"Spider [{self.name}] running preflight check")

        # 检查必要的配置
        if not self.base_url:
            raise ValueError(f"Spider [{self.name}] missing base_url")

        if not ctx.keyword:
            raise ValueError("Search keyword is required")

        # 初始化HTTP客户端
        if self._client is None:
            self._client = self._create_client(ctx)

    async def _post_process(self, result: CrawlResult, ctx: SpiderContext) -> None:
        """
        后置处理

        对爬取结果进行后处理。

        Args:
            result: 爬取结果
            ctx: 爬虫上下文
        """
        logger.debug(f"Spider [{self.name}] running post process")

        # 清理和验证数据
        valid_items = []
        for item in result.items:
            if self._validate_item(item):
                valid_items.append(item)
            else:
                logger.warning(f"Invalid item filtered: {item.title}")

        result.items = valid_items

    def _validate_item(self, item: JobItem) -> bool:
        """
        验证职位数据有效性

        Args:
            item: 职位数据

        Returns:
            bool: 是否有效
        """
        # 必须有职位名称和公司名称
        if not item.title or not item.company:
            return False

        # 必须有有效的URL
        if not item.url or not item.url.startswith("http"):
            return False

        return True

    def _create_client(self, ctx: SpiderContext) -> httpx.AsyncClient:
        """
        创建HTTP客户端

        Args:
            ctx: 爬虫上下文

        Returns:
            httpx.AsyncClient: 配置好的HTTP客户端
        """
        # 默认请求头
        default_headers = {
            "User-Agent": self._get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # 合并自定义请求头
        headers = {**default_headers, **ctx.headers}

        # 客户端配置
        config: dict[str, Any] = {
            "headers": headers,
            "timeout": httpx.Timeout(ctx.timeout),
            "follow_redirects": True,
            "http2": True,
        }

        # 代理配置
        if ctx.proxy:
            config["proxies"] = ctx.proxy

        return httpx.AsyncClient(**config)

    def _get_random_ua(self) -> str:
        """
        获取随机User-Agent

        Returns:
            str: User-Agent字符串
        """
        ua_list = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            # Chrome on Mac
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        ]
        return random.choice(ua_list)

    async def _fetch(
        self,
        url: str,
        ctx: SpiderContext,
        method: str = "GET",
        use_browser: bool = False,
        **kwargs: Any,
    ) -> Optional[httpx.Response]:
        """
        发送HTTP请求

        Args:
            url: 请求URL
            ctx: 爬虫上下文
            method: 请求方法
            use_browser: 是否使用浏览器渲染（用于反爬网站）
            **kwargs: 传递给httpx的额外参数

        Returns:
            httpx.Response: 响应对象，失败返回None
        """
        if use_browser:
            return await self._fetch_browser(url, ctx)

        if self._client is None:
            self._client = self._create_client(ctx)

        for attempt in range(ctx.max_retries):
            try:
                # 添加随机延迟
                await asyncio.sleep(ctx.get_delay())

                # 更新User-Agent
                self._client.headers["User-Agent"] = self._get_random_ua()

                logger.debug(f"Spider [{self.name}] fetching: {url} (attempt {attempt + 1})")

                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()

                return response

            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"Spider [{self.name}] HTTP error {e.response.status_code} for {url}"
                )
                if e.response.status_code in (403, 429):
                    # 被封禁或限流，增加延迟
                    await asyncio.sleep(ctx.get_delay() * 2)

            except httpx.RequestError as e:
                logger.warning(f"Spider [{self.name}] request error for {url}: {e}")

            except Exception as e:
                logger.error(f"Spider [{self.name}] unexpected error for {url}: {e}")

        return None

    async def _fetch_browser(
        self,
        url: str,
        ctx: SpiderContext,
        wait_selector: str | None = None,
        wait_timeout: int = 30000,
    ) -> Optional[httpx.Response]:
        """
        使用浏览器渲染获取页面（用于反爬网站）

        使用 Playwright 进行浏览器渲染，可以处理 JavaScript 动态内容和验证码。

        Args:
            url: 请求URL
            ctx: 爬虫上下文
            wait_selector: 等待特定元素出现
            wait_timeout: 等待超时时间（毫秒）

        Returns:
            httpx.Response: 响应对象（包含渲染后的HTML）
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return None

        for attempt in range(ctx.max_retries):
            try:
                logger.debug(f"Spider [{self.name}] browser fetching: {url} (attempt {attempt + 1})")

                async with async_playwright() as p:
                    # 启动浏览器
                    browser_args = []
                    if ctx.proxy:
                        browser_args.append(f"--proxy-server={ctx.proxy}")

                    browser = await p.chromium.launch(
                        headless=True,
                        args=browser_args,
                    )

                    # 创建上下文
                    browser_context = await browser.new_context(
                        user_agent=self._get_random_ua(),
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN",
                    )

                    page = await browser_context.new_page()

                    # 访问页面
                    response = await page.goto(url, timeout=ctx.timeout * 1000, wait_until="domcontentloaded")

                    if response is None:
                        await browser.close()
                        continue

                    # 等待特定元素或默认等待
                    if wait_selector:
                        try:
                            await page.wait_for_selector(wait_selector, timeout=wait_timeout)
                        except Exception as e:
                            logger.warning(f"Selector not found: {e}")
                    else:
                        # 默认等待页面加载
                        await page.wait_for_load_state("networkidle", timeout=wait_timeout)

                    # 获取渲染后的HTML
                    content = await page.content()

                    await browser.close()

                    # 构造响应对象
                    mock_response = httpx.Response(
                        status_code=200,
                        content=content.encode(),
                        request=httpx.Request("GET", url),
                    )

                    logger.debug(f"Spider [{self.name}] browser fetch success, content length: {len(content)}")
                    return mock_response

            except Exception as e:
                logger.warning(f"Spider [{self.name}] browser fetch error for {url}: {e}")
                await asyncio.sleep(ctx.get_delay())

        return None

    async def close(self) -> None:
        """关闭爬虫，释放资源"""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.debug(f"Spider [{self.name}] closed")

    async def __aenter__(self) -> "BaseSpider":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()
