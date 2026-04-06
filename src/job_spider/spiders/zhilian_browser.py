"""
智联招聘爬虫 - 浏览器模式

使用 Playwright 进行浏览器自动化，支持：
1. 手动登录并保存登录状态
2. 自动处理验证码（需人工首次处理）
3. 加载已保存的登录状态进行爬取

使用方法：
1. 首次运行：python main.py crawl zhilian-browser -k "Python" -c "北京" --login
   - 会打开浏览器，手动登录并处理验证码
   - 登录状态会保存到 data/browser_state/

2. 后续运行：python main.py crawl zhilian-browser -k "Python" -c "北京"
   - 自动加载已保存的登录状态
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from rich.console import Console

from config.settings import get_settings
from .base import (
    BaseSpider,
    CrawlResult,
    JobItem,
    SpiderContext,
    SpiderRegistry,
)

logger = logging.getLogger(__name__)
console = Console()


@SpiderRegistry.register
class ZhilianBrowserSpider(BaseSpider):
    """
    智联招聘爬虫 - 浏览器模式

    使用 Playwright 模拟真实浏览器行为，绕过反爬检测。

    Features:
        - 支持手动登录并保存登录状态
        - 自动加载已保存的 Cookies
        - 支持无头/有头模式切换
        - 智能等待页面加载

    Attributes:
        name: 爬虫名称
        login_url: 登录页面 URL
        search_url: 搜索页面 URL
    """

    name = "zhilian-browser"
    version = "1.0.0"
    base_url = "https://www.zhaopin.com"
    login_url = "https://passport.zhaopin.com/login"
    search_url = "https://sou.zhaopin.com"

    # 城市编码映射
    CITY_CODES = {
        "北京": "530",
        "上海": "538",
        "广州": "763",
        "深圳": "765",
        "杭州": "653",
        "成都": "801",
        "武汉": "736",
        "南京": "635",
        "西安": "854",
        "重庆": "854",
        "苏州": "636",
        "天津": "531",
        "长沙": "749",
        "郑州": "719",
        "合肥": "654",
        "厦门": "682",
    }

    def __init__(self) -> None:
        super().__init__()
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """
        执行搜索

        Args:
            ctx: 爬虫上下文

        Returns:
            CrawlResult: 爬取结果
        """
        # 检查是否需要登录模式
        need_login = ctx.extra.get("login", False)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return CrawlResult(success=False, error="Playwright not installed")

        all_items: list[JobItem] = []
        current_page = ctx.page
        max_pages = 5  # 最大页数限制

        async with async_playwright() as p:
            # 创建浏览器
            self._browser = await p.chromium.launch(
                headless=not need_login,  # 登录模式显示浏览器
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            # 创建浏览器上下文（加载已保存的状态）
            self._context = await self._create_browser_context(ctx)

            # 创建页面
            self._page = await self._context.new_page()

            # 设置额外的浏览器特征
            await self._setup_page()

            try:
                # 如果需要登录
                if need_login:
                    await self._handle_login(ctx)
                else:
                    # 检查登录状态
                    await self._check_login_status()

                # 开始爬取
                while current_page <= max_pages:
                    items = await self._crawl_page(ctx, current_page)
                    if not items:
                        break

                    all_items.extend(items)

                    if len(all_items) >= ctx.limit:
                        break

                    current_page += 1
                    await asyncio.sleep(ctx.get_delay())

            except Exception as e:
                logger.error(f"Crawl failed: {e}")
                return CrawlResult(success=False, error=str(e))

            finally:
                # 保存浏览器状态
                await self._save_browser_state()

                await self._browser.close()

        return CrawlResult(
            success=len(all_items) > 0,
            items=all_items[:ctx.limit],
            total_count=len(all_items),
            page=current_page,
            metadata={"source": self.name},
        )

    async def _create_browser_context(self, ctx: SpiderContext):
        """创建浏览器上下文，加载已保存的状态"""
        browser_state_dir = get_settings().storage.browser_state_dir
        state_file = browser_state_dir / "zhilian_state.json"

        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        # 如果存在已保存的状态，加载它
        if state_file.exists():
            logger.info("Loading saved browser state...")
            context_options["storage_state"] = str(state_file)
            self._logged_in = True

        return await self._browser.new_context(**context_options)

    async def _setup_page(self):
        """设置页面特征，绕过检测"""
        # 注入脚本隐藏自动化特征
        await self._page.add_init_script("""
            // 隐藏 webdriver 属性
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 修改 plugins 长度
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 修改 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });

            // 隐藏自动化相关的属性
            window.chrome = {
                runtime: {}
            };
        """)

    async def _handle_login(self, ctx: SpiderContext):
        """处理登录流程"""
        logger.info("Opening login page...")
        await self._page.goto(self.login_url, wait_until="domcontentloaded")

        console.print("\n[yellow]请在浏览器中完成登录：[/yellow]")
        console.print("1. 扫码或输入账号密码登录")
        console.print("2. 处理验证码（如果有）")
        console.print("3. 登录成功后按 Enter 继续...")

        # 等待用户完成登录
        input("\n按 Enter 继续...")

        # 验证登录状态
        await self._check_login_status()
        self._logged_in = True

    async def _check_login_status(self):
        """检查登录状态"""
        # 访问个人中心检查登录状态
        await self._page.goto("https://i.zhaopin.com/", wait_until="domcontentloaded")

        # 检查是否有用户信息
        try:
            await self._page.wait_for_selector(".user-info, .username", timeout=5000)
            logger.info("Login verified successfully")
            self._logged_in = True
        except Exception:
            logger.warning("Not logged in or session expired")
            self._logged_in = False

    async def _save_browser_state(self):
        """保存浏览器状态"""
        if not self._logged_in:
            return

        browser_state_dir = get_settings().storage.browser_state_dir
        browser_state_dir.mkdir(parents=True, exist_ok=True)
        state_file = browser_state_dir / "zhilian_state.json"

        try:
            await self._context.storage_state(path=str(state_file))
            logger.info(f"Browser state saved to {state_file}")
        except Exception as e:
            logger.warning(f"Failed to save browser state: {e}")

    async def _crawl_page(self, ctx: SpiderContext, page_num: int) -> list[JobItem]:
        """爬取单页数据"""
        city_code = self.CITY_CODES.get(ctx.location, ctx.location)
        url = f"{self.search_url}/?kw={ctx.keyword}&jl={city_code}&p={page_num}"

        logger.info(f"Crawling page {page_num}: {url}")
        await self._page.goto(url, wait_until="domcontentloaded")

        # 等待职位列表加载
        try:
            await self._page.wait_for_selector(
                ".joblist-box__item, [class*='job-item'], .positionlist .item",
                timeout=15000
            )
        except Exception:
            logger.warning(f"No job items found on page {page_num}")
            return []

        # 获取页面内容
        content = await self._page.content()
        items = self._parse_jobs(content, ctx)

        logger.info(f"Found {len(items)} jobs on page {page_num}")
        return items

    def _parse_jobs(self, html: str, ctx: SpiderContext) -> list[JobItem]:
        """解析职位数据"""
        from parsel import Selector

        selector = Selector(html)
        items: list[JobItem] = []

        # 尝试多种选择器
        job_selectors = [
            ".joblist-box__item",
            ".positionlist .item",
            "[class*='job-item']",
            "[class*='JobItem']",
        ]

        job_nodes = []
        for sel in job_selectors:
            job_nodes = selector.css(sel)
            if job_nodes:
                break

        for node in job_nodes:
            try:
                item = self._parse_job_node(node, ctx)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug(f"Failed to parse job node: {e}")
                continue

        return items

    def _parse_job_node(self, node, ctx: SpiderContext) -> Optional[JobItem]:
        """解析单个职位节点"""
        # 提取标题
        title_selectors = [
            ".jobinfo__top-title a::text",
            ".job-name a::text",
            "a[class*='title']::text",
            "h3 a::text",
        ]

        title = ""
        for sel in title_selectors:
            title = node.css(sel).get("")
            if title:
                break
        title = title.strip() if title else ""

        if not title:
            return None

        # 提取公司
        company_selectors = [
            ".companyinfo__top a::text",
            ".company-name a::text",
            "a[class*='company']::text",
        ]

        company = ""
        for sel in company_selectors:
            company = node.css(sel).get("")
            if company:
                break
        company = company.strip() if company else ""

        # 提取链接
        link = node.css("a::attr(href)").get("")
        if link and not link.startswith("http"):
            link = self.base_url + link if link.startswith("/") else self.search_url + "/" + link

        # 提取薪资
        salary_raw = node.css(".jobinfo__top-salary::text, .salary::text, [class*='salary']::text").get("")
        salary_raw = salary_raw.strip() if salary_raw else ""
        salary_min, salary_max = self._parse_salary(salary_raw)

        # 提取地点
        location = node.css(".jobinfo__top-location::text, .city::text, [class*='location']::text").get("")
        location = location.strip() if location else ""

        # 提取经验和学历
        detail_items = node.css(".jobinfo__detail li::text").getall()
        experience = detail_items[0].strip() if len(detail_items) > 0 else ""
        education = detail_items[1].strip() if len(detail_items) > 1 else ""

        return JobItem(
            title=title,
            company=company,
            url=link,
            source=self.name,
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
            location=location or ctx.location,
            experience=experience,
            education=education,
            job_id=node.attrib.get("data-jobid", ""),
        )

    def _parse_salary(self, salary_text: str) -> tuple[Optional[int], Optional[int]]:
        """解析薪资"""
        if not salary_text or "面议" in salary_text:
            return None, None

        # 使用通用解析
        from .zhilian import parse_salary
        return parse_salary(salary_text)
