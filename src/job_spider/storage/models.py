"""
数据模型定义

包含 SQLAlchemy 数据库模型和 Pydantic 验证模型。
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""

    pass


class JobStatus(str, Enum):
    """职位状态枚举"""

    ACTIVE = "active"
    EXPIRED = "expired"
    CLOSED = "closed"


class JobRaw(Base):
    """
    原始职位数据表

    存储从爬虫获取的原始数据，便于后续处理和问题排查。
    """

    __tablename__ = "job_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="批次ID")
    source: Mapped[str] = mapped_column(String(50), nullable=False, comment="数据来源")
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="原始JSON数据")
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="爬取时间"
    )

    # 索引
    __table_args__ = (
        Index("ix_job_raw_batch_id", "batch_id"),
        Index("ix_job_raw_source", "source"),
        Index("ix_job_raw_crawl_time", "crawl_time"),
    )

    def __repr__(self) -> str:
        return f"<JobRaw(id={self.id}, batch_id={self.batch_id}, source={self.source})>"


class JobProcessed(Base):
    """
    处理后职位数据表

    存储经过清洗和标准化的职位数据。
    """

    __tablename__ = "job_processed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, comment="职位唯一ID")
    source: Mapped[str] = mapped_column(String(50), nullable=False, comment="数据来源")

    # 职位基本信息
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="职位名称")
    company: Mapped[str] = mapped_column(String(200), nullable=False, comment="公司名称")

    # 薪资信息
    salary_min: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, comment="最低薪资(K)"
    )
    salary_max: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, comment="最高薪资(K)"
    )
    salary_avg: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, comment="平均薪资(K)"
    )

    # 工作地点
    city: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="城市")
    district: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="区县")
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="详细地址")

    # 职位要求
    experience: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="经验要求")
    education: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="学历要求")

    # 职位详情
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="职位描述")
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, comment="技能要求列表")

    # 公司信息
    company_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="公司规模")
    company_industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="行业")
    company_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="融资阶段")

    # 元数据
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="职位链接")
    publish_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="爬取时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobStatus.ACTIVE.value, comment="职位状态"
    )

    # 关联原始数据
    raw_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("job_raw.id", ondelete="SET NULL"), nullable=True, comment="原始数据ID"
    )
    raw: Mapped[Optional[JobRaw]] = relationship("JobRaw", backref="processed_jobs")

    # 索引和约束
    __table_args__ = (
        Index("ix_job_processed_source", "source"),
        Index("ix_job_processed_title", "title"),
        Index("ix_job_processed_company", "company"),
        Index("ix_job_processed_city", "city"),
        Index("ix_job_processed_salary_avg", "salary_avg"),
        Index("ix_job_processed_status", "status"),
        Index("ix_job_processed_crawl_time", "crawl_time"),
        Index("ix_job_processed_city_title", "city", "title"),
        UniqueConstraint("job_id", name="uq_job_processed_job_id"),
    )

    def __repr__(self) -> str:
        return f"<JobProcessed(job_id={self.job_id}, title={self.title}, company={self.company})>"


class CrawlTask(Base):
    """
    爬取任务表

    记录爬虫任务的执行状态和统计信息。
    """

    __tablename__ = "crawl_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="任务ID")
    spider_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="爬虫名称")
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="批次ID")

    # 任务配置
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="任务配置")

    # 执行状态
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", comment="任务状态"
    )
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="开始时间")
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")

    # 统计信息
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="总数量")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="成功数量")
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败数量")

    # 错误信息
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 索引
    __table_args__ = (
        Index("ix_crawl_task_spider_name", "spider_name"),
        Index("ix_crawl_task_batch_id", "batch_id"),
        Index("ix_crawl_task_status", "status"),
        Index("ix_crawl_task_created_at", "created_at"),
        UniqueConstraint("task_id", name="uq_crawl_task_task_id"),
    )

    def __repr__(self) -> str:
        return f"<CrawlTask(task_id={self.task_id}, spider_name={self.spider_name}, status={self.status})>"


# ==================== Pydantic 模型 ====================


class JobCreate(BaseModel):
    """
    职位创建模型

    用于创建新职位数据的验证。
    """

    job_id: str = Field(..., min_length=1, max_length=100, description="职位唯一ID")
    source: str = Field(..., min_length=1, max_length=50, description="数据来源")
    title: str = Field(..., min_length=1, max_length=200, description="职位名称")
    company: str = Field(..., min_length=1, max_length=200, description="公司名称")

    salary_min: Optional[Decimal] = Field(None, ge=0, description="最低薪资(K)")
    salary_max: Optional[Decimal] = Field(None, ge=0, description="最高薪资(K)")
    salary_avg: Optional[Decimal] = Field(None, ge=0, description="平均薪资(K)")

    city: Optional[str] = Field(None, max_length=50, description="城市")
    district: Optional[str] = Field(None, max_length=50, description="区县")
    address: Optional[str] = Field(None, max_length=200, description="详细地址")

    experience: Optional[str] = Field(None, max_length=50, description="经验要求")
    education: Optional[str] = Field(None, max_length=50, description="学历要求")

    description: Optional[str] = Field(None, description="职位描述")
    skills: Optional[list[str]] = Field(None, description="技能要求列表")

    company_size: Optional[str] = Field(None, max_length=50, description="公司规模")
    company_industry: Optional[str] = Field(None, max_length=100, description="行业")
    company_stage: Optional[str] = Field(None, max_length=50, description="融资阶段")

    url: Optional[str] = Field(None, max_length=500, description="职位链接")
    publish_time: Optional[datetime] = Field(None, description="发布时间")
    status: str = Field(default=JobStatus.ACTIVE.value, description="职位状态")

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        """验证薪资范围：最高薪资应大于等于最低薪资"""
        salary_min = info.data.get("salary_min")
        if v is not None and salary_min is not None and v < salary_min:
            raise ValueError("最高薪资不能小于最低薪资")
        return v

    @field_validator("skills", mode="before")
    @classmethod
    def validate_skills(cls, v: Any) -> Optional[list[str]]:
        """验证技能列表"""
        if v is None:
            return None
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s).strip() for s in v if s]
        return None


class JobResponse(BaseModel):
    """
    职位响应模型

    用于API响应的数据模型。
    """

    id: int
    job_id: str
    source: str
    title: str
    company: str

    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    salary_avg: Optional[Decimal] = None

    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None

    experience: Optional[str] = None
    education: Optional[str] = None

    description: Optional[str] = None
    skills: Optional[list[str]] = None

    company_size: Optional[str] = None
    company_industry: Optional[str] = None
    company_stage: Optional[str] = None

    url: Optional[str] = None
    publish_time: Optional[datetime] = None
    crawl_time: datetime
    status: str

    model_config = {"from_attributes": True}


class SpiderConfig(BaseModel):
    """
    爬虫配置模型

    用于爬虫任务的配置参数。
    """

    spider_name: str = Field(..., min_length=1, max_length=100, description="爬虫名称")
    start_urls: list[str] = Field(default_factory=list, description="起始URL列表")
    keywords: Optional[list[str]] = Field(None, description="搜索关键词")
    cities: Optional[list[str]] = Field(None, description="目标城市")
    max_pages: int = Field(default=10, ge=1, le=1000, description="最大页数")
    concurrent_requests: int = Field(default=5, ge=1, le=50, description="并发请求数")
    request_delay: float = Field(default=1.0, ge=0, le=60, description="请求间隔(秒)")
    timeout: int = Field(default=30, ge=5, le=300, description="请求超时(秒)")
    retry_times: int = Field(default=3, ge=0, le=10, description="重试次数")

    # 存储配置
    save_raw: bool = Field(default=True, description="是否保存原始数据")
    deduplicate: bool = Field(default=True, description="是否去重")

    # 代理配置
    proxy_enabled: bool = Field(default=False, description="是否启用代理")
    proxy_url: Optional[str] = Field(None, description="代理地址")


class SpiderResult(BaseModel):
    """
    爬取结果模型

    用于记录爬虫任务的执行结果。
    """

    task_id: str = Field(..., description="任务ID")
    batch_id: str = Field(..., description="批次ID")
    spider_name: str = Field(..., description="爬虫名称")

    status: str = Field(..., description="任务状态")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")

    total_count: int = Field(default=0, ge=0, description="总数量")
    success_count: int = Field(default=0, ge=0, description="成功数量")
    fail_count: int = Field(default=0, ge=0, description="失败数量")

    error_message: Optional[str] = Field(None, description="错误信息")

    # 统计信息
    items: list[JobCreate] = Field(default_factory=list, description="爬取的职位列表")

    @property
    def duration(self) -> Optional[float]:
        """计算执行时长(秒)"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count
