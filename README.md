# Job Spider - 招聘数据爬虫系统

企业级招聘网站数据采集系统，支持智联招聘、前程无忧、Boss直聘等主流招聘平台。

## 功能特性

- 🔍 多平台职位搜索
- 📊 薪资数据分析
- 🔄 定时自动爬取
- 📈 数据导出（CSV/Excel）
- 🛡️ 完善的反爬策略
- 🐳 Docker 容器化部署
- 📊 Prometheus 监控告警

## 架构设计

### 整体架构图

```mermaid
graph TB
    subgraph CLI["🖥️ CLI 入口层"]
        MAIN[main.py]
        CLICK[click 命令]
    end

    subgraph CORE["⚙️ 核心引擎层"]
        ENGINE[SpiderEngine<br/>爬虫引擎]
        REGISTRY[SpiderRegistry<br/>爬虫注册中心]
        SHUTDOWN[ShutdownManager<br/>优雅关闭]
        CONTEXT[SpiderContext<br/>执行上下文]
    end

    subgraph SPIDERS["🕷️ 爬虫层"]
        BASE[BaseSpider<br/>爬虫基类]
        ZHILIAN[ZhilianSpider<br/>智联招聘]
        ZHILIAN_BW[ZhilianBrowserSpider<br/>智联浏览器模式]
        JOB51[Job51Spider<br/>前程无忧]
        MOCK[MockSpider<br/>测试爬虫]
    end

    subgraph MW["🛡️ 中间件层"]
        RESILIENCE[ResilientClient<br/>弹性客户端]
        RATE[RateLimiter<br/>限流器]
        CB[CircuitBreaker<br/>熔断器]
        RETRY[RetryPolicy<br/>重试策略]
        UA[UserAgentRotator<br/>UA轮换]
        PROXY[ProxyManager<br/>代理管理]
    end

    subgraph PIPELINE["🔄 数据管道层"]
        PARSER[ParserStage<br/>数据解析]
        VALIDATOR[ValidateStage<br/>数据验证]
        DEDUPER[DedupStage<br/>数据去重]
    end

    subgraph STORAGE["💾 存储层"]
        DB[Database<br/>数据库管理]
        REPO[JobRepository<br/>数据仓库]
        MODELS[JobProcessed<br/>数据模型]
        BACKUP[DatabaseBackup<br/>数据备份]
        EXPORTER[Exporter<br/>数据导出]
    end

    subgraph OBS["📈 可观测性层"]
        METRICS[SpiderMetrics<br/>指标收集]
        METRICS_SVR[MetricsServer<br/>指标服务]
        HEALTH[HealthServer<br/>健康检查]
        TRACING[Tracing<br/>链路追踪]
    end

    subgraph SCHED["⏰ 调度层"]
        SCHEDULER[APScheduler<br/>定时任务]
    end

    MAIN --> CLICK
    CLICK --> ENGINE
    ENGINE --> REGISTRY
    ENGINE --> CONTEXT
    ENGINE --> SHUTDOWN

    REGISTRY --> BASE
    BASE --> ZHILIAN
    BASE --> ZHILIAN_BW
    BASE --> JOB51
    BASE --> MOCK

    BASE --> RESILIENCE
    RESILIENCE --> RATE
    RESILIENCE --> CB
    RESILIENCE --> RETRY
    BASE --> UA
    BASE --> PROXY

    BASE --> PIPELINE
    PIPELINE --> PARSER
    PIPELINE --> VALIDATOR
    PIPELINE --> DEDUPER

    PIPELINE --> STORAGE
    STORAGE --> DB
    DB --> REPO
    REPO --> MODELS
    STORAGE --> BACKUP
    STORAGE --> EXPORTER

    ENGINE --> OBS
    OBS --> METRICS
    METRICS --> METRICS_SVR
    OBS --> HEALTH
    OBS --> TRACING

    SCHEDULER --> ENGINE
```

### 爬虫执行流程

```mermaid
sequenceDiagram
    participant CLI as CLI
    participant Engine as SpiderEngine
    participant Registry as SpiderRegistry
    participant Spider as BaseSpider
    participant MW as ResilientClient
    participant Pipeline as DataPipeline
    participant Storage as JobRepository
    participant Metrics as SpiderMetrics

    CLI->>Engine: run_one(spider_name, ctx)
    Engine->>Registry: get_spider(spider_name)
    Registry-->>Engine: Spider实例
    Engine->>Spider: setup(ctx)
    
    loop 分页爬取
        Engine->>Spider: run(ctx)
        Spider->>MW: request(url)
        
        MW->>MW: 检查熔断器状态
        MW->>MW: 获取限流令牌
        MW->>MW: 执行请求(带重试)
        MW-->>Spider: Response
        
        Spider->>Spider: 解析数据
        Spider->>Pipeline: process(items)
        
        Pipeline->>Pipeline: ParserStage 解析
        Pipeline->>Pipeline: ValidateStage 验证
        Pipeline->>Pipeline: DedupStage 去重
        Pipeline-->>Spider: 有效数据
        
        Spider->>Metrics: 记录指标
        Spider-->>Engine: items
    end
    
    Engine->>Spider: teardown(ctx)
    Engine->>Storage: save(items)
    Engine-->>CLI: SpiderResult
```

### 弹性调用流程

```mermaid
flowchart TD
    A[请求入口] --> B{熔断器状态}
    
    B -->|OPEN| C[抛出 CircuitBreakerError]
    B -->|CLOSED/HALF_OPEN| D[获取限流令牌]
    
    D --> E[执行请求]
    E --> F{请求成功?}
    
    F -->|是| G[记录成功到熔断器]
    G --> H[返回结果]
    
    F -->|否| I{重试次数?}
    I -->|未达上限| J[计算退避延迟]
    J --> K[等待]
    K --> E
    
    I -->|已达上限| L[记录失败到熔断器]
    L --> M{熔断器阈值?}
    M -->|达到| N[打开熔断器]
    M -->|未达| O[抛出 RetryExhaustedError]
    N --> O
```

### 数据管道流程

```mermaid
flowchart LR
    subgraph Input
        A[原始数据]
    end
    
    subgraph ParserStage["解析阶段"]
        B[薪资解析<br/>parse_salary]
        C[经验解析<br/>parse_experience]
        D[学历解析<br/>parse_education]
    end
    
    subgraph ValidateStage["验证阶段"]
        E[字段验证<br/>job_id/title/company]
        F[格式验证<br/>url/salary范围]
    end
    
    subgraph DedupStage["去重阶段"]
        G[计算Hash<br/>job_id + source]
        H[检查重复]
    end
    
    subgraph Output
        I[有效数据]
        J[无效数据]
        K[重复数据]
    end
    
    A --> B --> C --> D
    D --> E --> F
    F -->|有效| G
    F -->|无效| J
    G --> H
    H -->|唯一| I
    H -->|重复| K
```

### 部署架构

```mermaid
graph TB
    subgraph Docker["Docker Compose"]
        SPIDER[Spider Service<br/>爬虫服务]
        SCHED[Scheduler Service<br/>调度服务]
    end
    
    subgraph Volumes["持久化存储"]
        DATA[(data/<br/>SQLite数据库)]
        LOGS[(logs/<br/>日志文件)]
        OUTPUT[(output/<br/>导出文件)]
        BROWSER[(browser_state/<br/>登录状态)]
    end
    
    subgraph Monitoring["监控体系"]
        PROM[Prometheus<br/>指标采集]
        ALERT[AlertManager<br/>告警管理]
        GRAF[Grafana<br/>可视化]
    end
    
    subgraph Health["健康检查"]
        HC[/health<br/>存活探针]
        RD[/ready<br/>就绪探针]
    end
    
    SPIDER --> DATA
    SPIDER --> LOGS
    SPIDER --> OUTPUT
    SPIDER --> BROWSER
    
    SCHED --> DATA
    SCHED --> LOGS
    
    SPIDER --> PROM
    PROM --> ALERT
    PROM --> GRAF
    
    SPIDER --> HC
    SPIDER --> RD
```

## 快速开始

### 环境要求

- Python 3.10+
- uv（推荐）或 pip

### 安装

```bash
# 使用 uv（推荐）
uv sync --all-extras

# 或使用 pip
pip install -e ".[dev]"
```

### 使用

```bash
# 初始化项目
python main.py init

# 列出可用爬虫
python main.py list-spiders

# 爬取智联招聘数据
python main.py crawl zhilian -k "Python开发" -c "深圳" -l 100

# 使用浏览器模式（处理反爬）
python main.py crawl zhilian-browser -k "Python" -c "北京" --login

# 查看统计
python main.py stats

# 导出数据
python main.py export --format excel --output output/jobs.xlsx

# 启动健康检查服务
python main.py health --port 8080

# 启动指标服务
python main.py metrics-server --port 8000
```

## 项目结构

```
job-spider/
├── config/                    # 配置模块
│   ├── settings.py           # 配置管理（pydantic-settings）
│   └── logging.py            # 日志配置（structlog）
│
├── src/job_spider/
│   ├── core/                  # 核心模块
│   │   ├── engine.py         # 爬虫引擎
│   │   ├── registry.py       # 爬虫注册中心
│   │   ├── context.py        # 执行上下文
│   │   └── shutdown.py       # 优雅关闭管理
│   │
│   ├── spiders/               # 爬虫实现
│   │   ├── base.py           # 爬虫基类
│   │   ├── zhilian.py        # 智联招聘
│   │   ├── zhilian_browser.py# 智联浏览器模式
│   │   ├── job51.py          # 前程无忧
│   │   └── mock.py           # 测试爬虫
│   │
│   ├── middleware/            # 中间件
│   │   ├── resilience.py     # 弹性客户端（重试+熔断+限流）
│   │   ├── retry.py          # 重试策略
│   │   ├── circuit_breaker.py# 熔断器
│   │   ├── rate_limiter.py   # 限流器
│   │   ├── user_agent.py     # UA 轮换
│   │   └── proxy.py          # 代理管理
│   │
│   ├── pipeline/              # 数据管道
│   │   ├── base.py           # 管道基类
│   │   ├── parser.py         # 数据解析
│   │   ├── validator.py      # 数据验证
│   │   └── deduper.py        # 数据去重
│   │
│   ├── storage/               # 存储层
│   │   ├── database.py       # 数据库管理
│   │   ├── models.py         # 数据模型
│   │   ├── repository.py     # 数据仓库
│   │   ├── backup.py         # 数据备份
│   │   └── exporter.py       # 数据导出
│   │
│   ├── observability/         # 可观测性
│   │   ├── metrics.py        # 指标收集
│   │   ├── metrics_server.py # 指标服务
│   │   └── tracing.py        # 链路追踪
│   │
│   ├── health/                # 健康检查
│   │   └── server.py         # 健康服务
│   │
│   ├── scheduler/             # 调度器
│   │   └── scheduler.py      # 定时任务
│   │
│   └── utils/                 # 工具函数
│       ├── http.py           # HTTP 工具
│       └── parser.py         # 解析工具
│
├── monitoring/                # 监控配置
│   ├── prometheus.yml        # Prometheus 配置
│   ├── alertmanager.yml      # 告警路由
│   └── alerts.yml            # 告警规则
│
├── data/                      # 数据存储
├── output/                    # 导出文件
├── logs/                      # 日志
│
├── Dockerfile                 # Docker 构建
├── docker-compose.yml         # 容器编排
└── pyproject.toml            # 项目配置
```

## 支持的招聘网站

| 网站 | 状态 | 反爬等级 | 支持模式 |
|------|------|----------|----------|
| 智联招聘 | ✅ 已支持 | 低 | HTTP |
| 智联招聘 | ✅ 已支持 | 中 | 浏览器模式 |
| 前程无忧 | 🚧 开发中 | 中 | HTTP |
| Boss直聘 | 📋 计划中 | 高 | 浏览器模式 |

## 监控告警

### Prometheus 指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `job_spider_requests_total` | Counter | 请求总数 |
| `job_spider_request_duration_seconds` | Histogram | 请求延迟 |
| `job_spider_items_total` | Counter | 爬取数据量 |
| `job_spider_errors_total` | Counter | 错误数 |
| `job_spider_active_spiders` | Gauge | 活跃爬虫数 |

### 告警规则

- **SpiderHighFailureRate**: 爬虫失败率 > 50%
- **SpiderConsecutiveFailures**: 连续 5 次失败
- **SpiderHighLatency**: 请求延迟 P99 > 30s

## 开发

```bash
# 安装开发依赖
uv sync --all-extras

# 运行测试
uv run pytest tests/ --cov=src

# 代码检查
uv run ruff check src/ tests/

# 代码格式化
uv run black src/
uv run isort src/

# 类型检查
uv run mypy src/
```

## License

MIT
