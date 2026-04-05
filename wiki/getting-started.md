# 快速开始指南

本指南帮助您快速上手 Job Spider 招聘数据爬虫系统。

## 环境要求

- Python 3.11 或更高版本
- pip 包管理器
- Git（可选，用于克隆项目）

## 安装步骤

### 1. 获取项目代码

```bash
git clone <repository-url>
cd job-spider
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量（可选）

创建 `.env` 文件：

```env
# 基础配置
PROJECT_NAME=job-spider
DEBUG=false

# 数据库配置
DB_SQLITE_PATH=data/jobs.db

# 爬虫配置
SPIDER_DEFAULT_DELAY=1.0
SPIDER_MAX_CONCURRENT=5
SPIDER_TIMEOUT=30.0

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=console
```

## 基本使用

### 命令行接口

```bash
# 查看帮助
python -m job_spider --help

# 爬取智联招聘数据
python -m job_spider crawl zhilian --keyword "Python开发" --city "深圳"

# 爬取前程无忧数据
python -m job_spider crawl 51job --keyword "Java工程师" --city "上海"

# 查看数据统计
python -m job_spider stats

# 导出数据为 CSV
python -m job_spider export --format csv --output output/jobs.csv

# 导出数据为 Excel
python -m job_spider export --format excel --output output/jobs.xlsx
```

### 代码中使用

```python
import asyncio
from job_spider.core.engine import SpiderEngine
from job_spider.core.context import SpiderContext
from job_spider.core.registry import SpiderRegistry
from config.settings import get_settings

async def main():
    # 获取配置
    settings = get_settings()

    # 创建爬虫引擎
    engine = SpiderEngine(settings)

    # 创建爬取上下文
    ctx = SpiderContext(
        keyword="Python开发",
        location="深圳",
        page=1,
        page_size=20,
    )

    # 运行单个爬虫
    result = await engine.run_one("zhilian", ctx)

    if result.is_success:
        print(f"成功爬取 {result.item_count} 条数据")
        for item in result.data[:5]:
            print(f"- {item['title']} @ {item['company']}")
    else:
        print(f"爬取失败: {result.error}")

    # 运行多个爬虫
    results = await engine.run_many(["zhilian", "51job"], ctx)
    for r in results:
        print(f"{r.spider_name}: {r.status.value}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 项目结构

```
job-spider/
├── config/              # 配置文件
│   ├── settings.py      # 主配置类
│   ├── logging.py       # 日志配置
│   └── spiders/         # 爬虫特定配置
│       └── zhilian.yaml # 智联招聘配置
├── src/job_spider/      # 源代码
│   ├── core/            # 核心模块
│   │   ├── engine.py    # 爬虫引擎
│   │   ├── context.py   # 执行上下文
│   │   └── registry.py  # 爬虫注册表
│   ├── spiders/         # 爬虫实现
│   │   ├── base.py      # 基类
│   │   └── zhilian.py   # 智联招聘
│   ├── middleware/      # 中间件
│   │   ├── proxy.py     # 代理池
│   │   ├── rate_limiter.py  # 限流器
│   │   ├── circuit_breaker.py # 熔断器
│   │   └── retry.py     # 重试管理
│   ├── pipeline/        # 数据管道
│   │   ├── parser.py    # 解析器
│   │   ├── validator.py # 校验器
│   │   └── deduper.py   # 去重器
│   ├── storage/         # 存储层
│   │   ├── database.py  # 数据库管理
│   │   ├── models.py    # 数据模型
│   │   ├── repository.py # 数据仓库
│   │   └── exporter.py  # 导出器
│   ├── scheduler/       # 任务调度
│   │   └── scheduler.py # APScheduler 封装
│   ├── observability/   # 可观测性
│   │   ├── metrics.py   # 指标收集
│   │   └── tracing.py   # 链路追踪
│   └── utils/           # 工具函数
│       ├── http.py      # HTTP 客户端
│       └── parser.py    # 解析工具
├── data/                # 数据存储
├── output/              # 导出文件
├── logs/                # 日志文件
├── tests/               # 测试代码
│   ├── unit/            # 单元测试
│   └── integration/     # 集成测试
└── wiki/                # 项目文档
```

## 支持的招聘网站

| 网站 | 状态 | 反爬等级 | 说明 |
|------|------|----------|------|
| 智联招聘 | ✅ 已支持 | 低 | 推荐首选，数据量大 |
| 前程无忧 | ✅ 已支持 | 中 | 老牌平台，数据稳定 |
| Boss直聘 | 📋 计划中 | 高 | 需要浏览器模拟 |

## 常见问题

### Q: 如何添加代理？

```python
# 方式一：环境变量
export HTTP_PROXY="http://user:pass@host:port"

# 方式二：代码中设置
ctx = SpiderContext(
    keyword="Python",
    location="深圳",
    proxy="http://127.0.0.1:7890"
)
```

### Q: 如何修改爬取延迟？

```python
ctx = SpiderContext(
    keyword="Python",
    location="深圳",
    request_delay=(2.0, 5.0),  # 2-5秒随机延迟
)
```

### Q: 数据存储在哪里？

- SQLite 数据库：`data/jobs.db`
- 导出文件：`output/` 目录
- 日志文件：`logs/` 目录

## 下一步

- 阅读 [配置系统](configuration.md) 了解详细配置
- 阅读 [爬虫开发指南](spiders.md) 开发自定义爬虫
- 阅读 [反爬策略](anti-crawler.md) 了解反爬应对方案
