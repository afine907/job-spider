"""
前程无忧爬虫实现

前程无忧 (51job.com) 是国内主要的招聘网站之一。
本模块实现职位搜索和数据提取功能。

搜索URL: https://search.51job.com/list/{city_code},000000,0000,00,9,99,{keyword},2,{page}.html
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote

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
    - "15-25万/年" -> (12500, 20833)  # 转换为月薪
    - "1-2万/月" -> (10000, 20000)
    - "8-12K" -> (8000, 12000)
    - "8000-12000" -> (8000, 12000)
    - "面议" -> (None, None)

    Args:
        salary_text: 薪资字符串

    Returns:
        tuple: (最低薪资, 最高薪资)，单位为元/月
    """
    if not salary_text or "面议" in salary_text:
        return None, None

    salary_text = salary_text.strip()

    # 移除空格
    salary_text = salary_text.replace(" ", "")

    # 标准化单位
    salary_text = salary_text.lower()

    # 判断是否为年薪
    is_yearly = "年" in salary_text or "/年" in salary_text

    # 处理万/月格式
    wan_month_pattern = r"(\d+(?:\.\d+)?)[万]?\s*[-~至]\s*(\d+(?:\.\d+)?)[万]?/月"
    match = re.search(wan_month_pattern, salary_text)
    if match:
        min_val = float(match.group(1))
        max_val = float(match.group(2))
        # 万/月格式
        if "万" in salary_text or min_val < 100:
            min_salary = int(min_val * 10000)
            max_salary = int(max_val * 10000)
        else:
            min_salary = int(min_val)
            max_salary = int(max_val)
        return min_salary, max_salary

    # 处理万/年格式
    wan_year_pattern = r"(\d+(?:\.\d+)?)[万]?\s*[-~至]\s*(\d+(?:\.\d+)?)[万]?/年"
    match = re.search(wan_year_pattern, salary_text)
    if match:
        min_val = float(match.group(1))
        max_val = float(match.group(2))
        # 万/年格式，转换为月薪（除以12）
        if "万" in salary_text or min_val < 100:
            min_salary = int(min_val * 10000 / 12)
            max_salary = int(max_val * 10000 / 12)
        else:
            min_salary = int(min_val / 12)
            max_salary = int(max_val / 12)
        return min_salary, max_salary

    # 处理 K 格式
    k_pattern = r"(\d+(?:\.\d+)?)[Kk]\s*[-~至]\s*(\d+(?:\.\d+)?)[Kk]"
    match = re.search(k_pattern, salary_text)
    if match:
        min_val = float(match.group(1))
        max_val = float(match.group(2))
        min_salary = int(min_val * 1000)
        max_salary = int(max_val * 1000)
        return min_salary, max_salary

    # 尝试匹配纯数字格式
    num_pattern = r"(\d+)[-~至](\d+)"
    match = re.search(num_pattern, salary_text)
    if match:
        min_val = int(match.group(1))
        max_val = int(match.group(2))

        # 判断单位：如果数字较小，认为是K或万
        if min_val < 100:
            # 可能是万或K，根据上下文判断
            if "万" in salary_text:
                min_salary = min_val * 10000
                max_salary = max_val * 10000
            else:
                # 默认按K处理
                min_salary = min_val * 1000
                max_salary = max_val * 1000
        elif min_val < 1000:
            # 看起来像是K格式
            min_salary = min_val * 1000
            max_salary = max_val * 1000
        else:
            min_salary = min_val
            max_salary = max_val

        # 如果是年薪，转换为月薪
        if is_yearly:
            min_salary = int(min_salary / 12)
            max_salary = int(max_salary / 12)

        return min_salary, max_salary

    return None, None


@SpiderRegistry.register
class Job51Spider(BaseSpider):
    """
    前程无忧爬虫

    实现职位搜索和数据提取功能。

    Attributes:
        name: 爬虫名称 "51job"
        version: 版本号
        base_url: 前程无忧首页
        search_url: 搜索页面URL模板

    Example:
        >>> spider = Job51Spider()
        >>> ctx = SpiderContext(keyword="Python", location="上海")
        >>> result = await spider.search(ctx)

    CLI Usage:
        python main.py crawl 51job -k "Python" -c "上海" -l 50
    """

    name = "51job"
    version = "1.0.0"
    base_url = "https://www.51job.com"
    search_url = "https://search.51job.com/list/{city_code},000000,0000,00,9,99,{keyword},2,{page}.html"

    # 城市编码映射
    CITY_CODES = {
        "北京": "010000",
        "上海": "020000",
        "广州": "030200",
        "深圳": "040000",
        "杭州": "080200",
        "成都": "090200",
        "武汉": "180200",
        "南京": "070200",
        "西安": "200200",
        "重庆": "060000",
        "苏州": "070300",
        "天津": "050000",
        "长沙": "190200",
        "郑州": "170200",
        "合肥": "150200",
        "厦门": "120300",
        "青岛": "140300",
        "大连": "110300",
        "宁波": "080300",
        "无锡": "070500",
        "佛山": "030800",
        "东莞": "030900",
        "福州": "120200",
        "济南": "140200",
        "沈阳": "110200",
        "哈尔滨": "100200",
        "长春": "100300",
        "石家庄": "160200",
        "太原": "160400",
        "昆明": "250200",
        "贵阳": "240200",
        "南宁": "220200",
        "海口": "210200",
        "南昌": "130200",
        "兰州": "260200",
        "乌鲁木齐": "270200",
    }

    # 选择器配置
    selectors = {
        # 职位列表容器
        "job_list": ".j_joblist .e, .job-list .job-item, [class*='job-item']",
        # 职位标题
        "job_title": ".j_joblist .e .el a, .job-name a, .t1 a, [class*='job-title'] a",
        # 职位链接
        "job_link": ".j_joblist .e .el a, .job-name a, .t1 a",
        # 公司名称
        "company_name": ".j_joblist .e .er a, .company-name a, .t2 a",
        # 薪资
        "salary": ".j_joblist .e .sal, .salary, .t4",
        # 地点
        "location": ".j_joblist .e .d, .location, .t3",
        # 经验要求
        "experience": ".j_joblist .e .d .e1, .experience",
        # 学历要求
        "education": ".j_joblist .e .d .e2, .education",
        # 职位ID
        "job_id": "@data-jobid, @data-id",
    }

    def __init__(self) -> None:
        """初始化爬虫实例"""
        super().__init__()
        self._total_pages = 0

    def _build_search_url(self, keyword: str, city: str, page: int) -> str:
        """
        构建搜索URL

        Args:
            keyword: 搜索关键词
            city: 城市名称
            page: 页码

        Returns:
            str: 完整的搜索URL
        """
        # 获取城市编码
        city_code = self._get_city_code(city)

        # URL编码关键词
        encoded_keyword = quote(keyword, safe="")

        # 构建URL
        url = self.search_url.format(
            city_code=city_code,
            keyword=encoded_keyword,
            page=page,
        )

        return url

    def _get_city_code(self, city: str) -> str:
        """
        获取城市编码

        Args:
            city: 城市名称

        Returns:
            str: 城市编码，未找到时返回默认值
        """
        # 尝试完全匹配
        if city in self.CITY_CODES:
            return self.CITY_CODES[city]

        # 尝试部分匹配
        for key, code in self.CITY_CODES.items():
            if key in city or city in key:
                return code

        # 默认返回全国编码
        return "000000"

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
            search_url = self._build_search_url(
                keyword=ctx.keyword,
                city=ctx.location,
                page=current_page,
            )

            logger.info(f"Fetching page {current_page}: {search_url}")

            # 发送请求
            response = await self._fetch(search_url, ctx)

            if response is None:
                logger.error(f"Failed to fetch page {current_page}")
                break

            # 解析响应
            items, page_info = self._parse_search_result(response.text, ctx)

            all_items.extend(items)

            # 更新分页信息
            has_more = page_info.get("has_more", False)

            logger.info(
                f"Page {current_page}: got {len(items)} items, total: {len(all_items)}"
            )

            # 检查是否达到限制数量
            if ctx.page_size > 0 and len(all_items) >= ctx.page_size * 20:
                has_more = False

            current_page += 1

            # 检查是否还有更多数据
            if not items:
                has_more = False

        return CrawlResult(
            success=len(all_items) > 0,
            items=all_items[: ctx.page_size * 20] if ctx.page_size > 0 else all_items,
            total_count=len(all_items),
            page=current_page - 1,
            has_more=has_more,
            metadata={"source": self.name, "keyword": ctx.keyword, "city": ctx.location},
        )

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
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = self.base_url + url
            else:
                url = self.base_url + "/" + url

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

        # 尝试从地点字段解析经验和学历
        experience = ""
        education = ""

        # 地点字段通常包含: 地点 | 经验 | 学历
        if location:
            parts = re.split(r"[\|｜,/]", location)
            if len(parts) >= 1:
                location = parts[0].strip()
            if len(parts) >= 2:
                exp_text = parts[1].strip()
                if "年" in exp_text or "经验" in exp_text or "不限" in exp_text:
                    experience = exp_text
            if len(parts) >= 3:
                edu_text = parts[2].strip()
                if any(kw in edu_text for kw in ["本科", "大专", "硕士", "博士", "高中", "中专", "不限"]):
                    education = edu_text

        # 尝试从独立字段提取经验和学历
        exp_node = node.css(self.selectors["experience"])
        if not experience:
            experience = exp_node.css("::text").get("") or ""
            experience = experience.strip()

        edu_node = node.css(self.selectors["education"])
        if not education:
            education = edu_node.css("::text").get("") or ""
            education = education.strip()

        # 提取职位ID
        job_id = node.attrib.get("data-jobid", "") or node.attrib.get("data-id", "")

        # 如果没有从属性获取到，尝试从URL解析
        if not job_id and url:
            match = re.search(r"/(\d+)\.html", url)
            if match:
                job_id = match.group(1)

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
        total_page_text = selector.css(".p_in .td::text").get("")
        if total_page_text:
            match = re.search(r"共\s*(\d+)\s*页", total_page_text)
            if match:
                page_info["total_pages"] = int(match.group(1))

        # 尝试查找总数
        total_count_text = selector.css(".p_in .td::text").get("")
        if total_count_text:
            match = re.search(r"共\s*(\d+)\s*条", total_count_text)
            if match:
                page_info["total_count"] = int(match.group(1))

        # 尝试从其他位置查找总数
        result_count = selector.css(".result-count::text").get("")
        if result_count:
            match = re.search(r"(\d+)", result_count.replace(",", ""))
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

        # 提取职位要求
        requirements = selector.css(".job-requirement::text").get("")

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
            "requirements": requirements.strip(),
        })

        return item
