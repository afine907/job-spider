# 配置系统

Job Spider 使用 **pydantic-settings** 实现类型安全的配置管理，支持环境变量、.env 文件和代码配置。

## 配置结构

```
config/
├── __init__.py
├── settings.py      # 主配置类
├── logging.py       # 日志配置
└── spiders/         # 爬虫特定配置
    └── zhilian.yaml
```

## 主配置类

### Settings

```python
from config.settings import Settings, get_settings

# 获取配置单例
settings = get_settings()

# 基础配置
print(settings.project_name)  # job-spider
print(settings.version)        # 0.1.0
print(settings.debug)          # False

# 数据库配置
print(settings.database.sqlite_path)  # data/jobs.db

# 爬虫配置
print(settings.spider.default_delay)   # 1.0
print(settings.spider.max_concurrent)  # 5
print(settings.spider.timeout)         # 30.0
print(settings.spider.retry_times)     # 3

# 日志配置
print(settings.log.level)        # INFO
print(settings.log.format)       # console
print(settings.log.output_path)  # None
```

### 配置类详解

#### DatabaseConfig

```python
class DatabaseConfig(BaseSettings):
    sqlite_path: Path = Path("data/jobs.db")  # SQLite 数据库路径
```

#### SpiderConfig

```python
class SpiderConfig(BaseSettings):
    default_delay: float = 1.0      # 默认请求延迟（秒）
    max_concurrent: int = 5         # 最大并发数
    timeout: float = 30.0           # 请求超时（秒）
    retry_times: int = 3            # 重试次数
    retry_delay: float = 2.0        # 重试延迟（秒）
    user_agent: str = "..."         # 默认 User-Agent
```

#### LogConfig

```python
class LogConfig(BaseSettings):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "console"
    output_path: Path | None = None  # 日志文件路径
    include_trace: bool = True       # 是否包含追踪信息
```

## 环境变量配置

所有配置项都可通过环境变量覆盖。

### 环境变量命名规则

```
{前缀}_{字段名}
```

### 示例

```bash
# 基础配置
export PROJECT_NAME=my-spider
export DEBUG=true

# 数据库配置（前缀 DB_）
export DB_SQLITE_PATH=/path/to/database.db

# 爬虫配置（前缀 SPIDER_）
export SPIDER_DEFAULT_DELAY=2.0
export SPIDER_MAX_CONCURRENT=10
export SPIDER_TIMEOUT=60.0
export SPIDER_RETRY_TIMES=5

# 日志配置（前缀 LOG_）
export LOG_LEVEL=DEBUG
export LOG_FORMAT=json
export LOG_OUTPUT_PATH=logs/app.log
```

### 嵌套配置

使用双下划线 `__` 分隔嵌套层级：

```bash
# 等同于 settings.database.sqlite_path
export DATABASE__SQLITE_PATH=data/custom.db

# 等同于 settings.spider.max_concurrent
export SPIDER__MAX_CONCURRENT=10
```

## .env 文件配置

在项目根目录创建 `.env` 文件：

```env
# 基础配置
PROJECT_NAME=job-spider
VERSION=0.1.0
DEBUG=false

# 数据库配置
DB_SQLITE_PATH=data/jobs.db

# 爬虫配置
SPIDER_DEFAULT_DELAY=1.0
SPIDER_MAX_CONCURRENT=5
SPIDER_TIMEOUT=30.0
SPIDER_RETRY_TIMES=3
SPIDER_USER_AGENT=Mozilla/5.0 ...

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=console
```

## 爬虫特定配置

每个爬虫可以有独立的 YAML 配置文件。

### 配置文件位置

```
config/spiders/{spider_name}.yaml
```

### 示例：zhilian.yaml

```yaml
# 基本信息
name: zhilian
version: "1.0.0"
enabled: true

# 网站地址
base_url: https://www.zhaopin.com
search_url: https://sou.zhaopin.com

# 请求配置
request:
  delay:
    min: 1.0
    max: 3.0
  timeout: 30
  max_retries: 3
  concurrency: 1

# 分页配置
pagination:
  page_size: 20
  max_pages: 50
  start_page: 1

# User-Agent 池
user_agents:
  - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
  - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."

# CSS选择器配置
selectors:
  job_list:
    - ".joblist-box__item"
  job_title:
    - ".jobinfo__top .jobinfo__top-title a"
  company_name:
    - ".companyinfo__top a"
  salary:
    - ".jobinfo__top .jobinfo__top-salary"

# 城市编码映射
city_codes:
  北京: "530"
  上海: "538"
  深圳: "765"

# 反爬策略
anti_crawler:
  ua_rotation: true
  random_delay: true
  fake_referer: true
  cookie_management: true
```

### 加载爬虫配置

```python
import yaml
from pathlib import Path

def load_spider_config(spider_name: str) -> dict:
    config_path = Path(f"config/spiders/{spider_name}.yaml")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}
```

## 配置热更新

```python
from config.settings import reload_settings

# 重新加载配置
settings = reload_settings()
```

## 最佳实践

### 1. 敏感信息使用环境变量

```bash
# 不要将敏感信息写入 .env 文件
export PROXY_USER=username
export PROXY_PASS=password
```

### 2. 不同环境使用不同配置

```bash
# 开发环境
export DEBUG=true
export LOG_LEVEL=DEBUG

# 生产环境
export DEBUG=false
export LOG_LEVEL=INFO
export LOG_FORMAT=json
```

### 3. 配置验证

配置类使用 Pydantic 进行类型验证：

```python
# 自动验证类型
settings.spider.max_concurrent = "10"  # 自动转换为 int

# 验证范围
# retry_times: ge=0, le=10
settings.spider.retry_times = 15  # 抛出 ValidationError
```

### 4. 配置优先级

配置加载优先级从高到低：

1. 环境变量
2. .env 文件
3. 代码默认值

```python
# 代码中覆盖配置
settings = Settings(
    debug=True,
    spider=SpiderConfig(max_concurrent=10)
)
```
