# 存储层设计

Job Spider 采用分层存储架构，支持原始数据存储、处理后数据存储和数据导出。

## 存储架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        存储层 (Storage Layer)                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Raw Data   │  │   Processed  │  │  Meta Store  │          │
│  │   (原始数据)  │  │  (处理后数据) │  │   (元数据)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                 │                 │                   │
│         ▼                 ▼                 ▼                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    SQLite / PostgreSQL                       ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ Cache Layer  │  │   Exporter   │                             │
│  │  (缓存层)    │  │  (导出器)    │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## 数据模型

### SQLAlchemy 模型

#### JobRaw - 原始职位数据

```python
class JobRaw(Base):
    """存储爬虫获取的原始数据"""
    __tablename__ = "job_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), comment="批次ID")
    source: Mapped[str] = mapped_column(String(50), comment="数据来源")
    raw_data: Mapped[dict] = mapped_column(JSON, comment="原始JSON数据")
    crawl_time: Mapped[datetime] = mapped_column(DateTime, comment="爬取时间")
```

#### JobProcessed - 处理后数据

```python
class JobProcessed(Base):
    """存储清洗和标准化后的数据"""
    __tablename__ = "job_processed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), unique=True)
    source: Mapped[str] = mapped_column(String(50))

    # 职位基本信息
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))

    # 薪资信息
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    salary_avg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # 地点
    city: Mapped[str | None] = mapped_column(String(50))
    district: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(200))

    # 要求
    experience: Mapped[str | None] = mapped_column(String(50))
    education: Mapped[str | None] = mapped_column(String(50))

    # 详情
    description: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list | None] = mapped_column(JSON)

    # 公司信息
    company_size: Mapped[str | None] = mapped_column(String(50))
    company_industry: Mapped[str | None] = mapped_column(String(100))

    # 元数据
    url: Mapped[str | None] = mapped_column(String(500))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime)
    crawl_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20))

    # 关联原始数据
    raw_id: Mapped[int | None] = mapped_column(ForeignKey("job_raw.id"))
```

#### CrawlTask - 爬取任务

```python
class CrawlTask(Base):
    """记录爬虫任务执行状态"""
    __tablename__ = "crawl_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True)
    spider_name: Mapped[str] = mapped_column(String(100))
    batch_id: Mapped[str] = mapped_column(String(64))

    config: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)

    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text)
```

### Pydantic 模型

```python
class JobCreate(BaseModel):
    """职位创建模型"""

    job_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)

    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)

    city: str | None = Field(default=None, max_length=50)
    experience: str | None = Field(default=None, max_length=50)
    education: str | None = Field(default=None, max_length=50)

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v, info):
        min_sal = info.data.get("salary_min")
        if v and min_sal and v < min_sal:
            raise ValueError("最高薪资不能小于最低薪资")
        return v
```

## 数据库管理

### Database 类

```python
from job_spider.storage.database import Database

# 创建数据库实例
db = Database("sqlite:///data/jobs.db")

# 初始化（创建表）
await db.init()

# 获取会话
async with db.session() as session:
    # 使用 session
    pass
```

### 数据库配置

```python
# SQLite（默认）
db = Database("sqlite:///data/jobs.db")

# PostgreSQL（生产环境）
db = Database("postgresql://user:pass@localhost:5432/job_spider")
```

## 数据仓库 (Repository)

### 基本使用

```python
from job_spider.storage.repository import JobRepository

repo = JobRepository(session)

# 创建职位
job = await repo.create({
    "job_id": "zhilian_12345",
    "source": "zhilian",
    "title": "Python工程师",
    "company": "某科技公司",
})

# 查询职位
job = await repo.get_by_id("zhilian_12345")
jobs = await repo.get_by_city("深圳", limit=20)

# 更新职位
await repo.update(job.id, {"status": "expired"})

# 删除职位
await repo.delete(job.id)
```

### 查询方法

```python
class JobRepository:
    async def get_by_id(self, job_id: str) -> JobProcessed | None:
        """根据 job_id 查询"""
        ...

    async def get_by_city(
        self,
        city: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[JobProcessed]:
        """根据城市查询"""
        ...

    async def get_by_salary_range(
        self,
        min_salary: int,
        max_salary: int,
        limit: int = 100
    ) -> list[JobProcessed]:
        """根据薪资范围查询"""
        ...

    async def search(
        self,
        keyword: str,
        city: str | None = None,
        min_salary: int | None = None,
        max_salary: int | None = None,
        limit: int = 100
    ) -> list[JobProcessed]:
        """综合搜索"""
        ...

    async def count_by_city(self) -> dict[str, int]:
        """按城市统计"""
        ...

    async def count_by_source(self) -> dict[str, int]:
        """按来源统计"""
        ...

    async def get_salary_stats(self, city: str | None = None) -> dict:
        """薪资统计"""
        ...
```

### 批量操作

```python
# 批量创建
jobs = await repo.bulk_create([
    {"job_id": "1", "title": "Python", ...},
    {"job_id": "2", "title": "Java", ...},
])

# 批量更新
await repo.bulk_update_status(["id1", "id2"], "expired")

# 批量删除
await repo.bulk_delete(["id1", "id2"])
```

## 数据导出

### Exporter 类

```python
from job_spider.storage.exporter import Exporter

exporter = Exporter()

# 导出到 CSV
exporter.to_csv(jobs, "output/jobs.csv")

# 导出到 Excel
exporter.to_excel(jobs, "output/jobs.xlsx")

# 导出到 JSON
exporter.to_json(jobs, "output/jobs.json")
```

### 自定义导出格式

```python
class CustomExporter(Exporter):
    def to_custom(self, jobs: list[dict], output_path: str):
        """自定义导出格式"""
        with open(output_path, "w", encoding="utf-8") as f:
            for job in jobs:
                line = f"{job['title']}|{job['company']}|{job['salary_raw']}\n"
                f.write(line)
```

### 导出配置

```python
exporter = Exporter(
    include_columns=["title", "company", "salary_min", "salary_max", "city"],
    date_format="%Y-%m-%d",
    encoding="utf-8-sig",  # Excel 兼容中文
)
```

## 索引策略

### 已定义索引

```python
# JobProcessed 表索引
__table_args__ = (
    Index("ix_job_processed_source", "source"),
    Index("ix_job_processed_title", "title"),
    Index("ix_job_processed_company", "company"),
    Index("ix_job_processed_city", "city"),
    Index("ix_job_processed_salary_avg", "salary_avg"),
    Index("ix_job_processed_status", "status"),
    Index("ix_job_processed_crawl_time", "crawl_time"),
    Index("ix_job_processed_city_title", "city", "title"),  # 复合索引
)
```

### 查询优化建议

```python
# ✅ 使用索引字段查询
jobs = await repo.get_by_city("深圳")  # 使用 city 索引

# ✅ 使用复合索引
jobs = await session.execute(
    select(JobProcessed)
    .where(JobProcessed.city == "深圳")
    .where(JobProcessed.title.like("%Python%"))
)

# ❌ 避免全表扫描
jobs = await session.execute(
    select(JobProcessed).where(JobProcessed.description.like("%Python%"))
)
```

## 数据迁移

### SQLite 到 PostgreSQL

```python
async def migrate_to_postgres(sqlite_path: str, postgres_url: str):
    """从 SQLite 迁移到 PostgreSQL"""
    # 连接源数据库
    source_db = Database(f"sqlite:///{sqlite_path}")
    # 连接目标数据库
    target_db = Database(postgres_url)

    # 读取数据
    async with source_db.session() as session:
        jobs = await session.execute(select(JobProcessed))
        jobs = jobs.scalars().all()

    # 写入目标
    async with target_db.session() as session:
        for job in jobs:
            session.add(JobProcessed(**job.to_dict()))
        await session.commit()
```

## 数据清理

### 定期清理任务

```python
async def cleanup_old_data(days: int = 30):
    """清理过期数据"""
    cutoff = datetime.now() - timedelta(days=days)

    async with db.session() as session:
        # 清理过期职位
        await session.execute(
            delete(JobProcessed)
            .where(JobProcessed.crawl_time < cutoff)
        )

        # 更新状态
        await session.execute(
            update(JobProcessed)
            .where(JobProcessed.publish_time < cutoff)
            .values(status="expired")
        )

        await session.commit()
```

## 最佳实践

### 1. 使用事务

```python
async with db.session() as session:
    try:
        job1 = JobProcessed(...)
        session.add(job1)

        job2 = JobProcessed(...)
        session.add(job2)

        await session.commit()  # 原子提交
    except Exception:
        await session.rollback()
        raise
```

### 2. 批量插入优化

```python
# 使用 bulk_save_objects 提高性能
session.bulk_save_objects([JobProcessed(**data) for data in jobs])
await session.commit()
```

### 3. 连接池配置

```python
# PostgreSQL 连接池
engine = create_async_engine(
    postgres_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
```

### 4. 数据备份

```bash
# SQLite 备份
cp data/jobs.db data/jobs_backup_$(date +%Y%m%d).db

# PostgreSQL 备份
pg_dump job_spider > backup_$(date +%Y%m%d).sql
```
