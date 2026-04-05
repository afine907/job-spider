# 任务调度系统

Job Spider 使用 APScheduler 实现灵活的任务调度，支持定时爬取和周期性任务。

## 调度器架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      调度器层 (Scheduler Layer)                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │Task Scheduler│  │  Task Queue  │  │ Task Tracker │          │
│  │ (APScheduler)│  │  (任务队列)   │  │ (状态追踪)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## TaskScheduler 类

### 基本使用

```python
from job_spider.scheduler.scheduler import TaskScheduler

# 创建调度器
scheduler = TaskScheduler()

# 添加定时任务
scheduler.add_task(
    task_id="daily_crawl",
    func=crawl_jobs,
    trigger="cron",
    hour=9,
    minute=0,
)

# 启动调度器
scheduler.start()

# 停止调度器
scheduler.stop()
```

### 任务状态

```python
class TaskStatus(Enum):
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
```

### ScheduledTask 数据类

```python
@dataclass
class ScheduledTask:
    """定时任务定义"""

    id: str                      # 任务ID
    name: str                    # 任务名称
    func: Callable               # 执行函数
    trigger: str                 # 触发器类型：cron/interval
    trigger_args: dict           # 触发器参数
    enabled: bool = True         # 是否启用
    last_run: datetime | None    # 上次执行时间
    next_run: datetime | None    # 下次执行时间
    status: TaskStatus           # 任务状态
    metadata: dict = field(default_factory=dict)
```

## 触发器类型

### Cron 触发器

使用 cron 表达式定义执行时间：

```python
# 每天上午 9 点执行
scheduler.add_task(
    task_id="daily_morning",
    func=crawl_jobs,
    trigger="cron",
    hour=9,
    minute=0,
)

# 每周一至周五上午 9 点执行
scheduler.add_task(
    task_id="weekday_crawl",
    func=crawl_jobs,
    trigger="cron",
    day_of_week="mon-fri",
    hour=9,
)

# 每月 1 号凌晨执行
scheduler.add_task(
    task_id="monthly_report",
    func=generate_report,
    trigger="cron",
    day=1,
    hour=0,
)

# 每小时执行
scheduler.add_task(
    task_id="hourly_check",
    func=check_status,
    trigger="cron",
    minute=0,
)
```

### Interval 触发器

按固定间隔执行：

```python
# 每 30 分钟执行
scheduler.add_task(
    task_id="frequent_check",
    func=check_status,
    trigger="interval",
    minutes=30,
)

# 每 2 小时执行
scheduler.add_task(
    task_id="bi_hourly",
    func=sync_data,
    trigger="interval",
    hours=2,
)

# 每 10 秒执行（测试用）
scheduler.add_task(
    task_id="test_task",
    func=test_func,
    trigger="interval",
    seconds=10,
)
```

## 任务管理

### 添加任务

```python
# 添加一次性任务
task = scheduler.add_task(
    task_id="one_time",
    func=my_function,
    trigger="interval",
    seconds=60,
)

print(f"Task ID: {task.id}")
print(f"Next run: {task.next_run}")
```

### 移除任务

```python
# 移除任务
removed = scheduler.remove_task("task_id")
if removed:
    print("任务已移除")
else:
    print("任务不存在")
```

### 暂停/恢复任务

```python
# 暂停任务
scheduler.pause_task("task_id")

# 恢复任务
scheduler.resume_task("task_id")
```

### 立即执行

```python
# 立即执行任务（不等待定时）
success = await scheduler.run_task_now("task_id")
if success:
    print("任务已触发")
```

### 查询任务

```python
# 获取单个任务
task = scheduler.get_task("task_id")
if task:
    print(f"Status: {task.status}")
    print(f"Last run: {task.last_run}")
    print(f"Next run: {task.next_run}")

# 列出所有任务
tasks = scheduler.list_tasks()
for task in tasks:
    print(f"{task.id}: {task.status.value}")
```

## 上下文管理器

```python
# 使用上下文管理器自动启动/停止
with TaskScheduler() as scheduler:
    scheduler.add_task("task1", func1, trigger="interval", minutes=30)
    scheduler.add_task("task2", func2, trigger="cron", hour=9)
    # 程序结束前自动停止
```

## 便捷函数

### daily - 每日执行

```python
from job_spider.scheduler.scheduler import daily

@daily(hour=9, minute=30)
async def daily_crawl():
    """每天 9:30 执行"""
    await crawl_all_sites()
```

### hourly - 每小时执行

```python
from job_spider.scheduler.scheduler import hourly

@hourly
async def hourly_check():
    """每小时执行"""
    await check_proxy_health()
```

## 实际应用示例

### 定时爬取任务

```python
import asyncio
from job_spider.scheduler.scheduler import TaskScheduler
from job_spider.core.engine import SpiderEngine
from job_spider.core.context import SpiderContext
from config.settings import get_settings

async def crawl_zhilian():
    """爬取智联招聘"""
    settings = get_settings()
    engine = SpiderEngine(settings)

    ctx = SpiderContext(
        keyword="Python",
        location="深圳",
        page=1,
        page_size=20,
    )

    result = await engine.run_one("zhilian", ctx)
    print(f"爬取完成: {result.item_count} 条")

async def crawl_all_sites():
    """爬取所有网站"""
    settings = get_settings()
    engine = SpiderEngine(settings)

    ctx = SpiderContext(keyword="Python", location="深圳")

    results = await engine.run_all(ctx)
    total = sum(r.item_count for r in results)
    print(f"总计爬取: {total} 条")

async def generate_daily_report():
    """生成日报"""
    from job_spider.storage.repository import JobRepository

    # 统计今日数据
    repo = JobRepository()
    stats = await repo.get_daily_stats()

    # 生成报告
    report = f"""
    每日爬取报告
    ============
    总数据量: {stats['total']}
    新增数据: {stats['new']}
    按城市分布: {stats['by_city']}
    """

    # 发送邮件或保存文件
    save_report(report)

async def cleanup_old_data():
    """清理过期数据"""
    from datetime import timedelta
    from job_spider.storage.database import Database

    db = Database()
    await db.cleanup(days=30)

async def main():
    scheduler = TaskScheduler()

    # 添加定时任务
    scheduler.add_task(
        task_id="morning_crawl",
        func=crawl_all_sites,
        trigger="cron",
        hour=9,
        minute=0,
    )

    scheduler.add_task(
        task_id="evening_crawl",
        func=crawl_all_sites,
        trigger="cron",
        hour=18,
        minute=0,
    )

    scheduler.add_task(
        task_id="daily_report",
        func=generate_daily_report,
        trigger="cron",
        hour=20,
        minute=0,
    )

    scheduler.add_task(
        task_id="weekly_cleanup",
        func=cleanup_old_data,
        trigger="cron",
        day_of_week="sun",
        hour=3,
        minute=0,
    )

    scheduler.add_task(
        task_id="proxy_check",
        func=check_proxy_health,
        trigger="interval",
        minutes=30,
    )

    # 启动调度器
    scheduler.start()
    print("调度器已启动")

    try:
        # 保持运行
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        scheduler.stop()
        print("调度器已停止")

if __name__ == "__main__":
    asyncio.run(main())
```

### 动态任务管理

```python
class DynamicTaskManager:
    """动态任务管理器"""

    def __init__(self):
        self.scheduler = TaskScheduler()
        self.task_configs: dict[str, dict] = {}

    async def add_crawl_task(
        self,
        task_id: str,
        spider_name: str,
        keyword: str,
        city: str,
        schedule: dict,
    ):
        """添加爬取任务"""
        async def crawl_func():
            engine = SpiderEngine(get_settings())
            ctx = SpiderContext(keyword=keyword, location=city)
            await engine.run_one(spider_name, ctx)

        self.scheduler.add_task(
            task_id=task_id,
            func=crawl_func,
            trigger=schedule.get("trigger", "cron"),
            **schedule.get("args", {}),
        )

        self.task_configs[task_id] = {
            "spider": spider_name,
            "keyword": keyword,
            "city": city,
            "schedule": schedule,
        }

    def update_task(self, task_id: str, new_schedule: dict):
        """更新任务计划"""
        config = self.task_configs.get(task_id)
        if config:
            self.scheduler.remove_task(task_id)
            self.scheduler.add_task(
                task_id=task_id,
                func=config["func"],
                trigger=new_schedule.get("trigger", "cron"),
                **new_schedule.get("args", {}),
            )

    def list_tasks(self) -> list[dict]:
        """列出所有任务及配置"""
        tasks = self.scheduler.list_tasks()
        result = []
        for task in tasks:
            config = self.task_configs.get(task.id, {})
            result.append({
                "id": task.id,
                "status": task.status.value,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "config": config,
            })
        return result
```

## 任务持久化

### 保存任务状态

```python
import json
from pathlib import Path

class PersistentScheduler(TaskScheduler):
    """支持持久化的调度器"""

    def __init__(self, state_file: str = "data/scheduler_state.json"):
        super().__init__()
        self.state_file = Path(state_file)
        self._load_state()

    def _load_state(self):
        """加载任务状态"""
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                state = json.load(f)
                # 恢复任务状态
                self._restore_state(state)

    def _save_state(self):
        """保存任务状态"""
        state = {
            task_id: {
                "enabled": task.enabled,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "status": task.status.value,
            }
            for task_id, task in self._tasks.items()
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
```

## 错误处理

### 任务执行错误处理

```python
from job_spider.scheduler.scheduler import TaskScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

scheduler = TaskScheduler()

def job_error_listener(event):
    """任务错误监听器"""
    if event.exception:
        logger.error(
            f"Task {event.job_id} failed: {event.exception}",
            exc_info=event.exception,
        )
        # 发送告警
        send_alert(f"任务 {event.job_id} 执行失败")

def job_missed_listener(event):
    """任务错过监听器"""
    logger.warning(f"Task {event.job_id} was missed")

# 添加监听器
scheduler._scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
scheduler._scheduler.add_listener(job_missed_listener, EVENT_JOB_MISSED)
```

### 重试机制

```python
async def task_with_retry(
    func: Callable,
    max_retries: int = 3,
    retry_delay: float = 60.0,
):
    """带重试的任务包装器"""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise

# 使用
scheduler.add_task(
    task_id="retry_task",
    func=lambda: task_with_retry(crawl_jobs, max_retries=3),
    trigger="cron",
    hour=9,
)
```

## 监控与日志

### 任务执行日志

```python
import structlog

logger = structlog.get_logger(__name__)

async def logged_task(func: Callable, task_id: str):
    """带日志的任务"""
    log = logger.bind(task_id=task_id)

    log.info("任务开始执行")
    start_time = time.monotonic()

    try:
        result = await func()
        duration = time.monotonic() - start_time
        log.info("任务执行完成", duration=duration)
        return result

    except Exception as e:
        duration = time.monotonic() - start_time
        log.error("任务执行失败", error=str(e), duration=duration)
        raise
```

### 任务统计

```python
class TaskStats:
    """任务统计"""

    def __init__(self):
        self.execution_counts: dict[str, int] = {}
        self.error_counts: dict[str, int] = {}
        self.last_execution: dict[str, datetime] = {}

    def record_success(self, task_id: str):
        self.execution_counts[task_id] = self.execution_counts.get(task_id, 0) + 1
        self.last_execution[task_id] = datetime.now()

    def record_error(self, task_id: str):
        self.error_counts[task_id] = self.error_counts.get(task_id, 0) + 1

    def get_stats(self, task_id: str) -> dict:
        return {
            "executions": self.execution_counts.get(task_id, 0),
            "errors": self.error_counts.get(task_id, 0),
            "last_execution": self.last_execution.get(task_id),
        }
```

## 最佳实践

### 1. 任务拆分

将大型任务拆分为小任务：

```python
# ❌ 不推荐：一次性爬取所有
async def crawl_all():
    for city in CITIES:
        for keyword in KEYWORDS:
            await crawl(city, keyword)

# ✅ 推荐：拆分为多个任务
for city in CITIES:
    scheduler.add_task(
        task_id=f"crawl_{city}",
        func=lambda c=city: crawl_city(c),
        trigger="cron",
        hour=9,
        minute=random.randint(0, 59),  # 错开执行时间
    )
```

### 2. 资源限制

```python
# 使用信号量限制并发
MAX_CONCURRENT = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

async def limited_task(func):
    async with semaphore:
        return await func()
```

### 3. 健康检查

```python
async def health_check():
    """定期健康检查"""
    scheduler = get_scheduler()
    tasks = scheduler.list_tasks()

    for task in tasks:
        if task.status == TaskStatus.FAILED:
            logger.warning(f"Task {task.id} is in failed state")
            # 尝试恢复
            scheduler.resume_task(task.id)
```
