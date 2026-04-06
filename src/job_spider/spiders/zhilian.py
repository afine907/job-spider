"""
智联招聘爬虫

实现智联招聘网站的职位数据爬取。

搜索URL: https://sou.zhaopin.com/
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from parsel import Selector

from .base import (
    BaseSpider,
    CrawlResult,
    JobItem,
    SpiderContext,
    SpiderRegistry,
)

logger = logging.getLogger(__name__)


def parse_salary(salary_text: str) -> tuple[Optional[int], Optional[int]]:
    """
    解析薪资字符串

    支持格式：
    - "10K-20K" -> (10000, 20000)
    - "10k-20k" -> (10000, 20000)
    - "1万-2万" -> (10000, 20000)
    - "10000-20000" -> (10000, 20000)
    - "10-20K" -> (10000, 20000)
    - "面议" -> (None, None)

    Args:
        salary_text: 薪资字符串

    Returns:
        tuple: (最低薪资, 最高薪资)，单位为元/月
    """
    if not salary_text or "面议" in salary_text:
        return None, None

    salary_text = salary_text.strip()

    # 标准化：统一转换为大写K
    salary_text = salary_text.replace("k", "K").replace("万", "K")

    # 移除空格
    salary_text = salary_text.replace(" ", "")

    # 尝试匹配 K格式
    k_pattern = r"(\d+(?:\.\d+)?)[Kk]?[-~至](\d+(?:\.\d+)?)[Kk]"
    match = re.search(k_pattern, salary_text)

    if match:
        min_val = float(match.group(1))
        max_val = float(match.group(2))

        # 如果数字看起来像是"10K-20K"格式，乘以1000
        if "K" in salary_text.upper() or min_val < 100:
            min_salary = int(min_val * 1000)
            max_salary = int(max_val * 1000)
        else:
            min_salary = int(min_val)
            max_salary = int(max_val)

        return min_salary, max_salary

    # 尝试匹配纯数字格式
    num_pattern = r"(\d+)[-~至](\d+)"
    match = re.search(num_pattern, salary_text)

    if match:
        min_val = int(match.group(1))
        max_val = int(match.group(2))

        # 判断单位：如果数字较小，认为是K
        if min_val < 1000:
            min_salary = min_val * 1000
            max_salary = max_val * 1000
        else:
            min_salary = min_val
            max_salary = max_val

        return min_salary, max_salary

    return None, None


@SpiderRegistry.register
class ZhilianSpider(BaseSpider):
    """
    智联招聘爬虫

    实现职位搜索和数据提取功能。

    Attributes:
        name: 爬虫名称 "zhilian"
        version: 版本号
        base_url: 智联招聘首页
        search_url: 搜索页面URL
    """

    name = "zhilian"
    version = "1.0.0"
    base_url = "https://www.zhaopin.com"
    search_url = "https://sou.zhaopin.com"

    # 选择器配置
    selectors = {
        # 职位列表容器
        "job_list": ".joblist-box__item, .positionlist .item, [class*='job-item']",
        # 职位标题
        "job_title": ".jobinfo__top .jobinfo__top-title a, .job-name a, [class*='job-title'] a",
        # 职位链接
        "job_link": ".jobinfo__top .jobinfo__top-title a, .job-name a, [class*='job-title'] a",
        # 公司名称
        "company_name": ".companyinfo__top a, .company-name a, [class*='company-name'] a",
        # 薪资
        "salary": ".jobinfo__top .jobinfo__top-salary, .salary, [class*='salary']",
        # 地点
        "location": ".jobinfo__top .jobinfo__top-location, .city, [class*='location']",
        # 经验要求
        "experience": ".jobinfo__detail li:nth-child(1), .experience, [class*='experience']",
        # 学历要求
        "education": ".jobinfo__detail li:nth-child(2), .education, [class*='education']",
        # 职位ID
        "job_id": "@data-jobid, @data-position-id",
    }

    def __init__(self) -> None:
        super().__init__()
        self._total_pages = 0

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """
        搜索职位列表

        Args:
            ctx: 爬虫上下文

        Returns:
            CrawlResult: 爬取结果
        """
        all_items: list[JobItem] = []
        current_page = ctx.page
        has_more = True

        while has_more and current_page <= ctx.page_size:
            # 构建搜索URL
            search_url = self._build_search_url(ctx, current_page)

            logger.info(f"Fetching page {current_page}: {search_url}")

            # 发送请求（使用浏览器渲染模式绑定反爬）
            response = await self._fetch(search_url, ctx, use_browser=True)

            if response is None:
                logger.error(f"Failed to fetch page {current_page}")
                break

            # 解析响应
            items, page_info = self._parse_search_result(response.text, ctx)

            all_items.extend(items)

            # 更新分页信息
            has_more = page_info.get("has_more", False)
            total_count = page_info.get("total_count", 0)

            logger.info(
                f"Page {current_page}: got {len(items)} items, total: {len(all_items)}"
            )

            current_page += 1

            # 检查是否达到最大页数
            if current_page > ctx.page + ctx.page_size - 1:
                break

            # 检查是否还有更多数据
            if not items:
                has_more = False

        return CrawlResult(
            success=len(all_items) > 0,
            items=all_items,
            total_count=len(all_items),
            page=current_page - 1,
            has_more=has_more,
            metadata={"source": self.name, "keyword": ctx.keyword},
        )

    def _build_search_url(self, ctx: SpiderContext, page: int) -> str:
        """
        构建搜索URL

        Args:
            ctx: 爬虫上下文
            page: 页码

        Returns:
            str: 搜索URL
        """
        # 智联招聘搜索URL格式
        # https://sou.zhaopin.com/?jl=城市&kw=关键词&p=页码
        params: list[str] = []

        if ctx.keyword:
            params.append(f"kw={ctx.keyword}")

        if ctx.location:
            # 城市编码映射（简化版）
            city_code = self._get_city_code(ctx.location)
            params.append(f"jl={city_code}")

        params.append(f"p={page}")

        return f"{self.search_url}/?{'&'.join(params)}"

    def _get_city_code(self, city: str) -> str:
        """
        获取城市编码

        Args:
            city: 城市名称

        Returns:
            str: 城市编码
        """
        # 常见城市编码映射
        city_map = {
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

        # 尝试完全匹配
        if city in city_map:
            return city_map[city]

        # 尝试部分匹配
        for key, code in city_map.items():
            if key in city or city in key:
                return code

        # 默认返回城市名称
        return city

    def _parse_search_result(
        self, html: str, ctx: SpiderContext
    ) -> tuple[list[JobItem], dict[str, Any]]:
        """
        解析搜索结果页面

        Args:
            html: HTML内容
            ctx: 爬虫上下文

        Returns:
            tuple: (职位列表, 分页信息)
        """
        selector = Selector(html)
        items: list[JobItem] = []
        page_info: dict[str, Any] = {"has_more": False, "total_count": 0}

        # 提取职位列表
        job_nodes = selector.css(self.selectors["job_list"])

        logger.debug(f"Found {len(job_nodes)} job nodes")

        for node in job_nodes:
            try:
                item = self._parse_job_node(node, ctx)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse job node: {e}")
                continue

        # 解析分页信息
        page_info = self._parse_pagination(selector)

        return items, page_info

    def _parse_job_node(
        self, node: Selector, ctx: SpiderContext
    ) -> Optional[JobItem]:
        """
        解析单个职位节点

        Args:
            node: parsel选择器节点
            ctx: 爬虫上下文

        Returns:
            JobItem: 职位数据，解析失败返回None
        """
        # 提取职位标题
        title_node = node.css(self.selectors["job_title"])
        title = title_node.css("::text").get("") or title_node.attrib.get("title", "")
        title = title.strip()

        if not title:
            return None

        # 提取职位链接
        link_node = node.css(self.selectors["job_link"])
        url = link_node.attrib.get("href", "")

        if url and not url.startswith("http"):
            url = self.base_url + url if url.startswith("/") else self.search_url + "/" + url

        # 提取公司名称
        company_node = node.css(self.selectors["company_name"])
        company = company_node.css("::text").get("") or company_node.attrib.get("title", "")
        company = company.strip()

        # 提取薪资
        salary_node = node.css(self.selectors["salary"])
        salary_raw = salary_node.css("::text").get("") or ""
        salary_raw = salary_raw.strip()
        salary_min, salary_max = parse_salary(salary_raw)

        # 提取地点
        location_node = node.css(self.selectors["location"])
        location = location_node.css("::text").get("") or ""
        location = location.strip()

        # 提取经验要求
        exp_node = node.css(self.selectors["experience"])
        experience = exp_node.css("::text").get("") or ""
        experience = experience.strip()

        # 提取学历要求
        edu_node = node.css(self.selectors["education"])
        education = edu_node.css("::text").get("") or ""
        education = education.strip()

        # 提取职位ID
        job_id = node.attrib.get("data-jobid", "") or node.attrib.get("data-position-id", "")

        return JobItem(
            title=title,
            company=company,
            url=url,
            source=self.name,
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
            location=location,
            experience=experience,
            education=education,
            job_id=job_id,
            raw_data={
                "html": node.get(),
            },
        )

    def _parse_pagination(self, selector: Selector) -> dict[str, Any]:
        """
        解析分页信息

        Args:
            selector: parsel选择器

        Returns:
            dict: 分页信息
        """
        page_info: dict[str, Any] = {"has_more": False, "total_count": 0}

        # 尝试查找下一页链接
        next_page = selector.css("a.next::attr(href)").get()
        if next_page:
            page_info["has_more"] = True

        # 尝试查找总页数
        total_page_text = selector.css(".soupager__pageinfo::text").get("")
        if total_page_text:
            match = re.search(r"共\s*(\d+)\s*页", total_page_text)
            if match:
                page_info["total_pages"] = int(match.group(1))

        # 尝试查找总数
        total_count_text = selector.css(".search-results__count::text").get("")
        if total_count_text:
            match = re.search(r"共\s*(\d+)\s*个", total_count_text)
            if match:
                page_info["total_count"] = int(match.group(1))

        return page_info

    async def get_detail(self, url: str, ctx: SpiderContext) -> Optional[JobItem]:
        """
        获取职位详情

        Args:
            url: 职位详情页URL
            ctx: 爬虫上下文

        Returns:
            JobItem: 职位详情
        """
        response = await self._fetch(url, ctx)

        if response is None:
            return None

        selector = Selector(response.text)

        # 提取详细信息
        description = selector.css(".job-description::text").get("")
        company_desc = selector.css(".company-description::text").get("")

        # 创建基础职位信息
        item = JobItem(
            title=selector.css("h1.job-title::text").get("").strip(),
            company=selector.css(".company-name::text").get("").strip(),
            url=url,
            source=self.name,
        )

        # 添加详细描述
        item.raw_data.update({
            "description": description.strip(),
            "company_description": company_desc.strip(),
        })

        return item
