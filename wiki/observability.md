# 可观测性系统

Job Spider 实现了完整的可观测性系统，包括结构化日志、指标收集和链路追踪。

## 可观测性架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     可观测性层 (Observability)                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Structured   │  │   Metrics    │  │  Tracing     │          │
│  │    Logs      │  │  (指标收集)   │  │  (链路追踪)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                 │                 │                   │
│         ▼                 ▼                 ▼                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   console    │  │   memory     │  │  trace_id    │          │
│  │   json file  │  │   prometheus │  │  span_id     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 结构化日志

### 使用 structlog

```python
import structlog

logger = structlog.get_logger(__name__)

# 基本日志
logger.info("爬虫启动", spider_name="zhilian")
logger.error("请求失败", url="...", error="...")

# 带上下文
log = logger.bind(spider="zhilian", city="深圳")
log.info("开始爬取", keyword="Python")
log.info("爬取完成", count=100)
```

### 日志配置

```python
from config.logging import setup_logging

setup_logging(
    level="INFO",
    format="console",  # 或 "json"
    output_path="logs/app.log",
)
```

### 日志格式

#### Console 格式

```
2024-01-15 10:30:45 [info     ] 爬虫启动 [job_spider.core.engine] spider_name=zhilian city=深圳
2024-01-15 10:30:46 [info     ] 请求成功 [job_spider.spiders.zhilian] url=https://... status=200
```

#### JSON 格式

```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "info",
  "event": "爬虫启动",
  "logger": "job_spider.core.engine",
  "spider_name": "zhilian",
  "city": "深圳"
}
```

### 日志上下文

```python
from job_spider.core.context import SpiderContext

ctx = SpiderContext(
    keyword="Python",
    location="深圳",
    trace_id="abc123",  # 链路追踪ID
)

# 使用上下文
log = logger.bind(trace_id=ctx.trace_id)
log.info("处理请求", url="...")
```

## 指标收集

### MetricsCollector 类

```python
from job_spider.observability.metrics import MetricsCollector

metrics = MetricsCollector()

# 计数器
metrics.increment("spider_requests_total", labels={"spider": "zhilian"})
metrics.increment("spider_items_total", value=100, labels={"spider": "zhilian"})

# 仪表盘
metrics.gauge("spider_active_count", 5, labels={"spider": "zhilian"})

# 直方图
metrics.histogram("request_duration_seconds", 0.5, labels={"spider": "zhilian"})

# 计时
metrics.timing("crawl_duration_seconds", 10.5, labels={"spider": "zhilian"})
```

### 获取指标

```python
# 获取计数器
count = metrics.get_counter("spider_requests_total", labels={"spider": "zhilian"})

# 获取仪表盘
value = metrics.get_gauge("spider_active_count")

# 获取直方图统计
stats = metrics.get_histogram_stats("request_duration_seconds")
# {"min": 0.1, "max": 2.5, "avg": 0.5, "count": 100}

# 导出所有指标
all_metrics = metrics.export()
```

### 内置指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `spider_requests_total` | Counter | 总请求数 |
| `spider_items_total` | Counter | 爬取数据总数 |
| `spider_errors_total` | Counter | 错误总数 |
| `spider_active_count` | Gauge | 活跃爬虫数 |
| `request_duration_seconds` | Histogram | 请求耗时 |
| `crawl_duration_seconds` | Histogram | 爬取耗时 |
| `proxy_healthy_count` | Gauge | 健康代理数 |

### 集成到爬虫

```python
class MonitoredSpider(BaseSpider):
    """带监控的爬虫基类"""

    async def execute(self, ctx: SpiderContext) -> CrawlResult:
        metrics = get_metrics()

        # 记录开始
        metrics.increment("spider_requests_total", labels={"spider": self.name})
        metrics.gauge("spider_active_count", 1, labels={"spider": self.name})

        start_time = time.monotonic()

        try:
            result = await super().execute(ctx)

            # 记录成功
            metrics.increment("spider_items_total",
                            value=result.total_count,
                            labels={"spider": self.name})

            return result

        except Exception as e:
            # 记录错误
            metrics.increment("spider_errors_total", labels={"spider": self.name})
            raise

        finally:
            # 记录耗时
            duration = time.monotonic() - start_time
            metrics.timing("crawl_duration_seconds", duration, labels={"spider": self.name})
            metrics.gauge("spider_active_count", 0, labels={"spider": self.name})
```

## 链路追踪

### TraceContext

```python
from job_spider.observability.tracing import TraceContext, Span

# 创建追踪上下文
trace = TraceContext(
    trace_id="abc123",
    span_id="span001",
)

# 创建 Span
async with Span("crawl_job_list", trace) as span:
    span.set_attribute("spider", "zhilian")
    span.set_attribute("city", "深圳")

    # 子操作
    async with Span("fetch_page", trace) as child:
        child.set_attribute("url", "https://...")
        response = await fetch(url)

    span.set_attribute("items_count", len(items))
```

### 追踪信息传播

```python
class SpiderContext:
    keyword: str = ""
    location: str = ""

    # 追踪信息
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = ""
    parent_span_id: str = ""
```

### 分布式追踪

```
Trace: abc123
├── Span: spider_execute (10.5s)
│   ├── Span: preflight_check (0.1s)
│   ├── Span: fetch_list (5.2s)
│   │   ├── Span: request_page_1 (1.0s)
│   │   ├── Span: request_page_2 (1.1s)
│   │   └── Span: request_page_3 (1.2s)
│   ├── Span: parse_items (2.3s)
│   └── Span: save_to_db (2.9s)
```

### 日志关联

```python
logger.info(
    "处理请求",
    url="...",
    trace_id=ctx.trace_id,
    span_id=ctx.span_id,
)
```

## 告警系统

### 告警规则

```python
class AlertRule:
    """告警规则定义"""

    name: str
    condition: Callable[[dict], bool]
    severity: str  # info, warning, critical
    message: str

# 示例规则
rules = [
    AlertRule(
        name="high_error_rate",
        condition=lambda m: m["spider_errors_total"] / m["spider_requests_total"] > 0.1,
        severity="warning",
        message="错误率超过 10%",
    ),
    AlertRule(
        name="no_healthy_proxy",
        condition=lambda m: m["proxy_healthy_count"] == 0,
        severity="critical",
        message="没有可用的健康代理",
    ),
]
```

### 告警通知

```python
async def check_alerts(metrics: MetricsCollector, rules: list[AlertRule]):
    """检查告警规则"""
    data = metrics.export()

    for rule in rules:
        if rule.condition(data):
            await send_alert(
                severity=rule.severity,
                message=rule.message,
                rule_name=rule.name,
            )
```

## 监控面板

### 指标端点

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/metrics")
async def get_metrics():
    """Prometheus 格式指标"""
    metrics = get_metrics()
    return metrics.to_prometheus_format()
```

### 健康检查

```python
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "spiders": {
            "active": metrics.get_gauge("spider_active_count"),
            "total_requests": metrics.get_counter("spider_requests_total"),
        },
    }
```

### 统计接口

```python
@app.get("/stats")
async def get_stats():
    """统计接口"""
    return {
        "requests": {
            "total": metrics.get_counter("spider_requests_total"),
            "errors": metrics.get_counter("spider_errors_total"),
        },
        "items": {
            "total": metrics.get_counter("spider_items_total"),
        },
        "duration": metrics.get_histogram_stats("crawl_duration_seconds"),
    }
```

## 最佳实践

### 1. 结构化日志字段

使用一致的字段名称：

```python
# ✅ 推荐
logger.info("请求成功", spider="zhilian", url="...", status=200)

# ❌ 避免
logger.info(f"Spider {name} request to {url} returned {status}")
```

### 2. 指标命名规范

遵循 Prometheus 命名规范：

```python
# ✅ 推荐
spider_requests_total
request_duration_seconds
proxy_healthy_count

# ❌ 避免
total_requests
request_time
healthy_proxies
```

### 3. 追踪关键路径

```python
async def crawl_job(self, job_id: str, ctx: SpiderContext):
    async with Span("crawl_job", ctx) as span:
        span.set_attribute("job_id", job_id)

        # 关键子操作
        async with Span("fetch_detail", ctx):
            detail = await self.fetch_detail(job_id)

        async with Span("parse_data", ctx):
            parsed = self.parse(detail)

        return parsed
```

### 4. 日志级别使用

| 级别 | 使用场景 |
|------|----------|
| DEBUG | 详细调试信息 |
| INFO | 正常操作流程 |
| WARNING | 可恢复的异常 |
| ERROR | 需要关注的错误 |
| CRITICAL | 系统级故障 |

### 5. 指标基数控制

```python
# ✅ 低基数标签
labels={"spider": "zhilian", "status": "success"}

# ❌ 高基数标签（避免）
labels={"url": "https://...", "user_id": "12345"}
```

## 集成示例

### 完整监控示例

```python
import structlog
from job_spider.observability.metrics import MetricsCollector
from job_spider.observability.tracing import Span

logger = structlog.get_logger(__name__)
metrics = MetricsCollector()

class MonitoredCrawler:
    def __init__(self, spider_name: str):
        self.spider_name = spider_name
        self.log = logger.bind(spider=spider_name)

    async def crawl(self, ctx: SpiderContext):
        trace_id = ctx.trace_id
        log = self.log.bind(trace_id=trace_id)

        async with Span("crawl", ctx) as span:
            log.info("开始爬取")
            metrics.increment("spider_requests_total", labels={"spider": self.spider_name})

            start = time.monotonic()

            try:
                result = await self._do_crawl(ctx)

                metrics.increment("spider_items_total",
                                value=len(result.items),
                                labels={"spider": self.spider_name})
                log.info("爬取完成", items=len(result.items))

                return result

            except Exception as e:
                metrics.increment("spider_errors_total", labels={"spider": self.spider_name})
                log.error("爬取失败", error=str(e))
                span.record_exception(e)
                raise

            finally:
                duration = time.monotonic() - start
                metrics.timing("crawl_duration_seconds", duration, labels={"spider": self.spider_name})
                span.set_attribute("duration_seconds", duration)
```
