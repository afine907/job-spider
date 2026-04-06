# Job Spider Monitoring

Prometheus 指标导出和告警配置。

## 快速开始

### 1. 启动指标服务器

```bash
# 默认端口 8000
python main.py metrics-server

# 指定端口
python main.py metrics-server --port 9090
```

### 2. 访问指标端点

```
http://localhost:8000/metrics
```

## 可用指标

| 指标名称 | 类型 | 标签 | 描述 |
|---------|------|------|------|
| `job_spider_requests_total` | Counter | spider, status | 请求总数 |
| `job_spider_request_duration_seconds` | Histogram | spider | 请求延迟 |
| `job_spider_items_total` | Counter | spider | 爬取数据量 |
| `job_spider_errors_total` | Counter | spider, type | 错误计数 |
| `job_spider_active_spiders` | Gauge | - | 活跃爬虫数 |

### 指标示例

```
# HELP job_spider_requests_total Total count
# TYPE job_spider_requests_total counter
job_spider_requests_total{spider="zhilian",status="success"} 100.0
job_spider_requests_total{spider="zhilian",status="failed"} 5.0

# HELP job_spider_request_duration_seconds Duration histogram
# TYPE job_spider_request_duration_seconds histogram
job_spider_request_duration_seconds_bucket{spider="zhilian",le="0.1"} 50
job_spider_request_duration_seconds_bucket{spider="zhilian",le="0.5"} 80
job_spider_request_duration_seconds_bucket{spider="zhilian",le="+Inf"} 100
job_spider_request_duration_seconds_sum{spider="zhilian"} 45.2
job_spider_request_duration_seconds_count{spider="zhilian"} 100

# HELP job_spider_items_total Total count
# TYPE job_spider_items_total counter
job_spider_items_total{spider="zhilian"} 5000.0

# HELP job_spider_errors_total Total count
# TYPE job_spider_errors_total counter
job_spider_errors_total{spider="zhilian",type="timeout"} 2.0
```

## Prometheus 配置

### Docker Compose 示例

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'

  job-spider:
    build: .
    ports:
      - "8000:8000"
    command: python main.py metrics-server
```

### 启动服务

```bash
# 启动 Prometheus
prometheus --config.file=monitoring/prometheus.yml

# 启动 Alertmanager
alertmanager --config.file=monitoring/alertmanager.yml

# 启动指标服务器
python main.py metrics-server
```

## 告警规则

### 已配置的告警

| 告警名称 | 条件 | 严重程度 |
|---------|------|---------|
| SpiderHighFailureRate | 失败率 > 50% | critical |
| SpiderFailureRateWarning | 失败率 > 20% | warning |
| SpiderConsecutiveFailures | 5分钟内 >= 5 次错误 | critical |
| SpiderHighLatency | P99 延迟 > 30s | warning |
| SpiderCriticalLatency | P99 延迟 > 60s | critical |
| SpiderDown | 实例不可达 | critical |

### 查看告警

访问 Prometheus UI: http://localhost:9090/alerts

## Grafana 仪表板

### 导入仪表板

1. 添加 Prometheus 数据源: `http://prometheus:9090`
2. 创建仪表板，使用以下查询:

```promql
# 请求成功率
sum(rate(job_spider_requests_total{status="success"}[5m])) 
/ sum(rate(job_spider_requests_total[5m]))

# P99 延迟
histogram_quantile(0.99, 
  sum(rate(job_spider_request_duration_seconds_bucket[5m])) by (le, spider)
)

# 每秒爬取数据量
sum(rate(job_spider_items_total[5m])) by (spider)

# 错误率
sum(rate(job_spider_errors_total[5m])) by (spider, type)
```

## 代码集成

### 在爬虫中记录自定义指标

```python
from job_spider.observability.metrics import SpiderMetrics, metrics

# 记录请求
SpiderMetrics.record_request(
    spider="my_spider",
    status="success",
    duration=1.5,
)

# 记录数据量
SpiderMetrics.record_items("my_spider", 100)

# 记录错误
SpiderMetrics.record_error("my_spider", "network")

# 使用时间上下文管理器
with SpiderMetrics.time_request("my_spider"):
    # 执行请求...
    pass

# 自定义指标
metrics.gauge("custom_metric", 42.0, labels={"spider": "my_spider"})
```

### 运行时启动指标服务器

```python
from job_spider.observability import start_metrics_server
import asyncio

async def main():
    # 启动指标服务器
    server = await start_metrics_server(port=8000)

    # 执行爬虫任务...
    # ...

    # 停止服务器
    await server.stop()

asyncio.run(main())
```

## 文件说明

```
monitoring/
├── prometheus.yml    # Prometheus 配置
├── alertmanager.yml  # Alertmanager 配置
├── alerts.yml        # 告警规则
└── README.md         # 本文档
```
