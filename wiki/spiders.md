# 爬虫开发指南

本文档介绍如何开发自定义爬虫，包括基类继承、数据模型、注册机制等。

## 爬虫基类

所有爬虫必须继承 `BaseSpider` 基类：

```python
from job_spider.spiders.base import (
    BaseSpider,
    SpiderContext,
    JobItem,
    CrawlResult,
    SpiderRegistry,
)

@SpiderRegistry.register  # 注册爬虫
class MySpider(BaseSpider):
    name = "my_spider"       # 唯一标识
    version = "1.0.0"        # 版本号
    base_url = "https://example.com"  # 目标网站

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """实现搜索逻辑"""
        # ... 爬取代码
        return CrawlResult(
            success=True,
            items=[...],
            total_count=100,
            has_more=True
        )
```

## 核心概念

### SpiderContext - 爬虫上下文

包含爬虫执行过程中需要的所有信息：

```python
@dataclass
class SpiderContext:
    # 搜索参数
    keyword: str = ""        # 搜索关键词
    location: str = ""       # 工作地点
    page: int = 1            # 页码
    page_size: int = 20      # 每页数量

    # 请求配置
    request_delay: tuple[float, float] = (1.0, 3.0)  # 延迟范围
    timeout: float = 30.0    # 超时时间
    max_retries: int = 3     # 最大重试次数

    # 代理配置
    proxy: Optional[str] = None

    # 自定义请求头
    headers: dict[str, str] = field(default_factory=dict)

    # 扩展数据
    extra: dict[str, Any] = field(default_factory=dict)
```

使用示例：

```python
ctx = SpiderContext(
    keyword="Python开发",
    location="深圳",
    page=1,
    page_size=20,
    request_delay=(2.0, 5.0),
    timeout=60.0,
)

# 获取随机延迟
delay = ctx.get_delay()  # 2.0 ~ 5.0 之间
```

### JobItem - 职位数据模型

```python
@dataclass
class JobItem:
    # 基本信息（必填）
    title: str          # 职位名称
    company: str        # 公司名称
    url: str            # 职位链接
    source: str         # 来源网站

    # 薪资信息
    salary_raw: str = ""        # 原始薪资文本
    salary_min: Optional[int] = None  # 最低薪资（元/月）
    salary_max: Optional[int] = None  # 最高薪资（元/月）

    # 职位详情
    location: str = ""      # 工作地点
    experience: str = ""    # 经验要求
    education: str = ""     # 学历要求
    job_type: str = ""      # 工作类型

    # 公司信息
    company_size: str = ""      # 公司规模
    company_industry: str = ""  # 所属行业

    # 元数据
    job_id: str = ""                    # 职位ID
    published_at: Optional[datetime] = None  # 发布时间
    crawled_at: datetime = field(default_factory=datetime.now)

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)
```

### CrawlResult - 爬取结果

```python
@dataclass
class CrawlResult:
    success: bool                    # 是否成功
    items: list[JobItem]            # 职位列表
    total_count: int = 0            # 总数量
    page: int = 1                   # 当前页
    has_more: bool = False          # 是否有更多
    error: Optional[str] = None     # 错误信息
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 爬虫生命周期

```python
class MySpider(BaseSpider):
    async def execute(self, ctx: SpiderContext) -> CrawlResult:
        """
        执行流程（模板方法）：
        1. _preflight_check()  - 前置检查
        2. search()            - 执行爬取
        3. _post_process()     - 后置处理
        """
        pass
```

### 前置检查

```python
async def _preflight_check(self, ctx: SpiderContext) -> None:
    """检查必要的配置和初始化 HTTP 客户端"""
    # 检查 base_url
    if not self.base_url:
        raise ValueError(f"Spider [{self.name}] missing base_url")

    # 检查关键词
    if not ctx.keyword:
        raise ValueError("Search keyword is required")

    # 初始化 HTTP 客户端
    if self._client is None:
        self._client = self._create_client(ctx)
```

### 后置处理

```python
async def _post_process(self, result: CrawlResult, ctx: SpiderContext) -> None:
    """数据清洗和验证"""
    valid_items = []
    for item in result.items:
        if self._validate_item(item):
            valid_items.append(item)
    result.items = valid_items
```

## HTTP 请求

### 使用内置方法

```python
class MySpider(BaseSpider):
    async def search(self, ctx: SpiderContext) -> CrawlResult:
        # GET 请求
        response = await self._fetch(
            url="https://example.com/jobs",
            ctx=ctx,
            method="GET"
        )

        if response is None:
            return CrawlResult(success=False, error="请求失败")

        # 解析响应
        # ...
```

### HTTP 客户端配置

```python
def _create_client(self, ctx: SpiderContext) -> httpx.AsyncClient:
    """创建 HTTP 客户端"""
    default_headers = {
        "User-Agent": self._get_random_ua(),
        "Accept": "text/html,application/xhtml+xml...",
    }

    config = {
        "headers": {**default_headers, **ctx.headers},
        "timeout": httpx.Timeout(ctx.timeout),
        "follow_redirects": True,
        "http2": True,
    }

    if ctx.proxy:
        config["proxies"] = ctx.proxy

    return httpx.AsyncClient(**config)
```

### User-Agent 轮换

```python
def _get_random_ua(self) -> str:
    """获取随机 User-Agent"""
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
        # ...
    ]
    return random.choice(ua_list)
```

## 完整示例

### 智联招聘爬虫

```python
import asyncio
from job_spider.spiders.base import (
    BaseSpider,
    SpiderContext,
    JobItem,
    CrawlResult,
    SpiderRegistry,
)

@SpiderRegistry.register
class ZhilianSpider(BaseSpider):
    """智联招聘爬虫"""

    name = "zhilian"
    version = "1.0.0"
    base_url = "https://www.zhaopin.com"

    async def search(self, ctx: SpiderContext) -> CrawlResult:
        """搜索职位"""
        items = []

        # 构建搜索 URL
        url = self._build_search_url(ctx)

        # 发送请求
        response = await self._fetch(url, ctx)
        if response is None:
            return CrawlResult(success=False, error="请求失败")

        # 解析页面
        items = self._parse_jobs(response.text)

        return CrawlResult(
            success=True,
            items=items,
            total_count=len(items),
            has_more=self._has_next_page(response.text),
        )

    def _build_search_url(self, ctx: SpiderContext) -> str:
        """构建搜索 URL"""
        params = {
            "kw": ctx.keyword,
            "p": ctx.page,
        }
        if ctx.location:
            params["city"] = self._get_city_code(ctx.location)

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.base_url}/sou?{query}"

    def _parse_jobs(self, html: str) -> list[JobItem]:
        """解析职位列表"""
        from parsel import Selector

        items = []
        selector = Selector(text=html)

        for job_el in selector.css(".joblist-box__item"):
            item = JobItem(
                title=job_el.css(".jobinfo__top-title a::text").get() or "",
                company=job_el.css(".companyinfo__top a::text").get() or "",
                url=job_el.css(".jobinfo__top-title a::attr(href)").get() or "",
                source=self.name,
                salary_raw=job_el.css(".jobinfo__top-salary::text").get() or "",
            )
            items.append(item)

        return items
```

## 爬虫注册

### 装饰器注册

```python
@SpiderRegistry.register
class MySpider(BaseSpider):
    name = "my_spider"
    # ...
```

### 手动注册

```python
SpiderRegistry._spiders["my_spider"] = MySpider
```

### 查询已注册爬虫

```python
# 列出所有爬虫
names = SpiderRegistry.list_spiders()
# ['zhilian', '51job', ...]

# 获取爬虫实例
spider = SpiderRegistry.get_spider("zhilian")
```

## 爬虫引擎

```python
from job_spider.core.engine import SpiderEngine

# 创建引擎
engine = SpiderEngine(settings)

# 运行单个爬虫
result = await engine.run_one("zhilian", ctx)

# 运行多个爬虫（并发）
results = await engine.run_many(["zhilian", "51job"], ctx)

# 运行所有爬虫
results = await engine.run_all(ctx)
```

## 最佳实践

### 1. 错误处理

```python
async def search(self, ctx: SpiderContext) -> CrawlResult:
    try:
        # 爬取逻辑
        pass
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            # 被封禁
            return CrawlResult(success=False, error="被封禁")
        raise
    except Exception as e:
        return CrawlResult(success=False, error=str(e))
```

### 2. 资源清理

```python
async with MySpider() as spider:
    result = await spider.execute(ctx)
# 自动调用 spider.close()
```

### 3. 数据验证

```python
def _validate_item(self, item: JobItem) -> bool:
    """验证职位数据有效性"""
    if not item.title or not item.company:
        return False
    if not item.url or not item.url.startswith("http"):
        return False
    return True
```

### 4. 分页处理

```python
async def crawl_all_pages(self, ctx: SpiderContext) -> list[JobItem]:
    """爬取所有页面"""
    all_items = []
    page = 1

    while True:
        ctx.page = page
        result = await self.search(ctx)

        if not result.success or not result.items:
            break

        all_items.extend(result.items)

        if not result.has_more:
            break

        page += 1
        await asyncio.sleep(ctx.get_delay())

    return all_items
```
