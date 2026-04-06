"""
数据仓库模块

提供职位数据的增删改查操作。
"""

from typing import Any, Optional, Sequence

from sqlalchemy import and_, func, or_, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from job_spider.storage.models import (
    JobCreate,
    JobProcessed,
    JobRaw,
    JobStatus,
    CrawlTask,
)


class JobRepository:
    """
    职位数据仓库

    提供对职位数据的CRUD操作，支持同步和异步两种方式。
    """

    def __init__(self, session: Session | AsyncSession) -> None:
        """
        初始化仓库。

        Args:
            session: 数据库会话（同步或异步）
        """
        self.session = session
        self._is_async = isinstance(session, AsyncSession)

    # ==================== 保存操作 ====================

    def save(self, job_data: JobCreate, raw_id: Optional[int] = None) -> JobProcessed:
        """
        保存单条职位数据（同步）。

        Args:
            job_data: 职位数据
            raw_id: 原始数据ID

        Returns:
            JobProcessed: 保存后的职位记录
        """
        job = JobProcessed(
            job_id=job_data.job_id,
            source=job_data.source,
            title=job_data.title,
            company=job_data.company,
            salary_min=job_data.salary_min,
            salary_max=job_data.salary_max,
            salary_avg=job_data.salary_avg,
            city=job_data.city,
            district=job_data.district,
            address=job_data.address,
            experience=job_data.experience,
            education=job_data.education,
            description=job_data.description,
            skills=job_data.skills,
            company_size=job_data.company_size,
            company_industry=job_data.company_industry,
            company_stage=job_data.company_stage,
            url=job_data.url,
            publish_time=job_data.publish_time,
            status=job_data.status,
            raw_id=raw_id,
        )
        self.session.add(job)
        self.session.flush()
        return job

    async def save_async(
        self, job_data: JobCreate, raw_id: Optional[int] = None
    ) -> JobProcessed:
        """
        保存单条职位数据（异步）。

        Args:
            job_data: 职位数据
            raw_id: 原始数据ID

        Returns:
            JobProcessed: 保存后的职位记录
        """
        job = JobProcessed(
            job_id=job_data.job_id,
            source=job_data.source,
            title=job_data.title,
            company=job_data.company,
            salary_min=job_data.salary_min,
            salary_max=job_data.salary_max,
            salary_avg=job_data.salary_avg,
            city=job_data.city,
            district=job_data.district,
            address=job_data.address,
            experience=job_data.experience,
            education=job_data.education,
            description=job_data.description,
            skills=job_data.skills,
            company_size=job_data.company_size,
            company_industry=job_data.company_industry,
            company_stage=job_data.company_stage,
            url=job_data.url,
            publish_time=job_data.publish_time,
            status=job_data.status,
            raw_id=raw_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    def save_batch(
        self, jobs_data: Sequence[JobCreate], raw_ids: Optional[dict[str, int]] = None
    ) -> int:
        """
        批量保存职位数据（同步）。

        Args:
            jobs_data: 职位数据列表
            raw_ids: job_id 到 raw_id 的映射

        Returns:
            int: 保存的记录数
        """
        if not jobs_data:
            return 0

        raw_ids = raw_ids or {}
        jobs = []
        for job_data in jobs_data:
            job = JobProcessed(
                job_id=job_data.job_id,
                source=job_data.source,
                title=job_data.title,
                company=job_data.company,
                salary_min=job_data.salary_min,
                salary_max=job_data.salary_max,
                salary_avg=job_data.salary_avg,
                city=job_data.city,
                district=job_data.district,
                address=job_data.address,
                experience=job_data.experience,
                education=job_data.education,
                description=job_data.description,
                skills=job_data.skills,
                company_size=job_data.company_size,
                company_industry=job_data.company_industry,
                company_stage=job_data.company_stage,
                url=job_data.url,
                publish_time=job_data.publish_time,
                status=job_data.status,
                raw_id=raw_ids.get(job_data.job_id),
            )
            jobs.append(job)

        self.session.add_all(jobs)
        self.session.flush()
        return len(jobs)

    async def save_batch_async(
        self, jobs_data: Sequence[JobCreate], raw_ids: Optional[dict[str, int]] = None
    ) -> int:
        """
        批量保存职位数据（异步）。

        Args:
            jobs_data: 职位数据列表
            raw_ids: job_id 到 raw_id 的映射

        Returns:
            int: 保存的记录数
        """
        if not jobs_data:
            return 0

        raw_ids = raw_ids or {}
        jobs = []
        for job_data in jobs_data:
            job = JobProcessed(
                job_id=job_data.job_id,
                source=job_data.source,
                title=job_data.title,
                company=job_data.company,
                salary_min=job_data.salary_min,
                salary_max=job_data.salary_max,
                salary_avg=job_data.salary_avg,
                city=job_data.city,
                district=job_data.district,
                address=job_data.address,
                experience=job_data.experience,
                education=job_data.education,
                description=job_data.description,
                skills=job_data.skills,
                company_size=job_data.company_size,
                company_industry=job_data.company_industry,
                company_stage=job_data.company_stage,
                url=job_data.url,
                publish_time=job_data.publish_time,
                status=job_data.status,
                raw_id=raw_ids.get(job_data.job_id),
            )
            jobs.append(job)

        self.session.add_all(jobs)
        await self.session.flush()
        return len(jobs)

    # ==================== 查询操作 ====================

    def exists(self, job_id: str) -> bool:
        """
        检查职位是否存在（同步）。

        Args:
            job_id: 职位ID

        Returns:
            bool: 是否存在
        """
        stmt = select(func.count()).select_from(JobProcessed).where(JobProcessed.job_id == job_id)
        result = self.session.execute(stmt)
        count = result.scalar()
        return count > 0

    async def exists_async(self, job_id: str) -> bool:
        """
        检查职位是否存在（异步）。

        Args:
            job_id: 职位ID

        Returns:
            bool: 是否存在
        """
        stmt = select(func.count()).select_from(JobProcessed).where(JobProcessed.job_id == job_id)
        result = await self.session.execute(stmt)
        count = result.scalar()
        return count > 0

    def find_by_id(self, job_id: str) -> Optional[JobProcessed]:
        """
        根据ID查询职位（同步）。

        Args:
            job_id: 职位ID

        Returns:
            Optional[JobProcessed]: 职位记录或None
        """
        stmt = select(JobProcessed).where(JobProcessed.job_id == job_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id_async(self, job_id: str) -> Optional[JobProcessed]:
        """
        根据ID查询职位（异步）。

        Args:
            job_id: 职位ID

        Returns:
            Optional[JobProcessed]: 职位记录或None
        """
        stmt = select(JobProcessed).where(JobProcessed.job_id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def find_by_city(
        self,
        city: str,
        limit: int = 100,
        offset: int = 0,
        status: str = JobStatus.ACTIVE.value,
    ) -> Sequence[JobProcessed]:
        """
        按城市查询职位（同步）。

        Args:
            city: 城市名称
            limit: 返回数量限制
            offset: 偏移量
            status: 职位状态

        Returns:
            Sequence[JobProcessed]: 职位列表
        """
        stmt = (
            select(JobProcessed)
            .where(and_(JobProcessed.city == city, JobProcessed.status == status))
            .order_by(JobProcessed.crawl_time.desc())
            .limit(limit)
            .offset(offset)
        )
        result = self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_city_async(
        self,
        city: str,
        limit: int = 100,
        offset: int = 0,
        status: str = JobStatus.ACTIVE.value,
    ) -> Sequence[JobProcessed]:
        """
        按城市查询职位（异步）。

        Args:
            city: 城市名称
            limit: 返回数量限制
            offset: 偏移量
            status: 职位状态

        Returns:
            Sequence[JobProcessed]: 职位列表
        """
        stmt = (
            select(JobProcessed)
            .where(and_(JobProcessed.city == city, JobProcessed.status == status))
            .order_by(JobProcessed.crawl_time.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    def find_by_keyword(
        self,
        keyword: str,
        fields: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
        status: str = JobStatus.ACTIVE.value,
    ) -> Sequence[JobProcessed]:
        """
        按关键词查询职位（同步）。

        Args:
            keyword: 搜索关键词
            fields: 搜索字段列表（默认：title, company, description）
            limit: 返回数量限制
            offset: 偏移量
            status: 职位状态

        Returns:
            Sequence[JobProcessed]: 职位列表
        """
        fields = fields or ["title", "company", "description"]
        search_pattern = f"%{keyword}%"

        conditions = []
        if "title" in fields:
            conditions.append(JobProcessed.title.ilike(search_pattern))
        if "company" in fields:
            conditions.append(JobProcessed.company.ilike(search_pattern))
        if "description" in fields:
            conditions.append(JobProcessed.description.ilike(search_pattern))
        if "city" in fields:
            conditions.append(JobProcessed.city.ilike(search_pattern))

        stmt = (
            select(JobProcessed)
            .where(and_(or_(*conditions), JobProcessed.status == status))
            .order_by(JobProcessed.crawl_time.desc())
            .limit(limit)
            .offset(offset)
        )
        result = self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_keyword_async(
        self,
        keyword: str,
        fields: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0,
        status: str = JobStatus.ACTIVE.value,
    ) -> Sequence[JobProcessed]:
        """
        按关键词查询职位（异步）。

        Args:
            keyword: 搜索关键词
            fields: 搜索字段列表（默认：title, company, description）
            limit: 返回数量限制
            offset: 偏移量
            status: 职位状态

        Returns:
            Sequence[JobProcessed]: 职位列表
        """
        fields = fields or ["title", "company", "description"]
        search_pattern = f"%{keyword}%"

        conditions = []
        if "title" in fields:
            conditions.append(JobProcessed.title.ilike(search_pattern))
        if "company" in fields:
            conditions.append(JobProcessed.company.ilike(search_pattern))
        if "description" in fields:
            conditions.append(JobProcessed.description.ilike(search_pattern))
        if "city" in fields:
            conditions.append(JobProcessed.city.ilike(search_pattern))

        stmt = (
            select(JobProcessed)
            .where(and_(or_(*conditions), JobProcessed.status == status))
            .order_by(JobProcessed.crawl_time.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    def find_by_conditions(
        self,
        conditions: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        descending: bool = True,
    ) -> Sequence[JobProcessed]:
        """
        按条件查询职位（同步）。

        Args:
            conditions: 查询条件字典
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序字段
            descending: 是否降序

        Returns:
            Sequence[JobProcessed]: 职位列表
        """
        stmt = select(JobProcessed)

        # 构建查询条件
        filters = []
        for key, value in conditions.items():
            if hasattr(JobProcessed, key) and value is not None:
                column = getattr(JobProcessed, key)
                if isinstance(value, (list, tuple)):
                    filters.append(column.in_(value))
                elif isinstance(value, str) and "%" in value:
                    filters.append(column.ilike(value))
                else:
                    filters.append(column == value)

        if filters:
            stmt = stmt.where(and_(*filters))

        # 排序
        if order_by and hasattr(JobProcessed, order_by):
            column = getattr(JobProcessed, order_by)
            stmt = stmt.order_by(column.desc() if descending else column.asc())
        else:
            stmt = stmt.order_by(JobProcessed.crawl_time.desc())

        stmt = stmt.limit(limit).offset(offset)
        result = self.session.execute(stmt)
        return result.scalars().all()

    # ==================== 统计操作 ====================

    def count(self, status: Optional[str] = None) -> int:
        """
        统计职位数量（同步）。

        Args:
            status: 职位状态（可选）

        Returns:
            int: 职位数量
        """
        stmt = select(func.count()).select_from(JobProcessed)
        if status:
            stmt = stmt.where(JobProcessed.status == status)
        result = self.session.execute(stmt)
        return result.scalar() or 0

    async def count_async(self, status: Optional[str] = None) -> int:
        """
        统计职位数量（异步）。

        Args:
            status: 职位状态（可选）

        Returns:
            int: 职位数量
        """
        stmt = select(func.count()).select_from(JobProcessed)
        if status:
            stmt = stmt.where(JobProcessed.status == status)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    def count_by_city(self) -> dict[str, int]:
        """
        按城市统计职位数量（同步）。

        Returns:
            dict[str, int]: 城市到数量的映射
        """
        stmt = (
            select(JobProcessed.city, func.count().label("count"))
            .where(JobProcessed.city.isnot(None))
            .group_by(JobProcessed.city)
            .order_by(func.count().desc())
        )
        result = self.session.execute(stmt)
        return {row.city: row.count for row in result}

    async def count_by_city_async(self) -> dict[str, int]:
        """
        按城市统计职位数量（异步）。

        Returns:
            dict[str, int]: 城市到数量的映射
        """
        stmt = (
            select(JobProcessed.city, func.count().label("count"))
            .where(JobProcessed.city.isnot(None))
            .group_by(JobProcessed.city)
            .order_by(func.count().desc())
        )
        result = await self.session.execute(stmt)
        return {row.city: row.count for row in result}

    def count_by_source(self) -> dict[str, int]:
        """
        按数据来源统计职位数量（同步）。

        Returns:
            dict[str, int]: 来源到数量的映射
        """
        stmt = (
            select(JobProcessed.source, func.count().label("count"))
            .group_by(JobProcessed.source)
            .order_by(func.count().desc())
        )
        result = self.session.execute(stmt)
        return {row.source: row.count for row in result}

    # ==================== 更新和删除操作 ====================

    def update_status(self, job_id: str, status: str) -> bool:
        """
        更新职位状态（同步）。

        Args:
            job_id: 职位ID
            status: 新状态

        Returns:
            bool: 是否更新成功
        """
        stmt = (
            update(JobProcessed)
            .where(JobProcessed.job_id == job_id)
            .values(status=status)
        )
        result = self.session.execute(stmt)
        return result.rowcount > 0

    async def update_status_async(self, job_id: str, status: str) -> bool:
        """
        更新职位状态（异步）。

        Args:
            job_id: 职位ID
            status: 新状态

        Returns:
            bool: 是否更新成功
        """
        stmt = (
            update(JobProcessed)
            .where(JobProcessed.job_id == job_id)
            .values(status=status)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    def delete(self, job_id: str) -> bool:
        """
        删除职位（同步）。

        Args:
            job_id: 职位ID

        Returns:
            bool: 是否删除成功
        """
        stmt = delete(JobProcessed).where(JobProcessed.job_id == job_id)
        result = self.session.execute(stmt)
        return result.rowcount > 0

    async def delete_async(self, job_id: str) -> bool:
        """
        删除职位（异步）。

        Args:
            job_id: 职位ID

        Returns:
            bool: 是否删除成功
        """
        stmt = delete(JobProcessed).where(JobProcessed.job_id == job_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    # ==================== 原始数据操作 ====================

    def save_raw(
        self, batch_id: str, source: str, raw_data: dict[str, Any]
    ) -> JobRaw:
        """
        保存原始数据（同步）。

        Args:
            batch_id: 批次ID
            source: 数据来源
            raw_data: 原始数据

        Returns:
            JobRaw: 保存后的原始数据记录
        """
        raw = JobRaw(
            batch_id=batch_id,
            source=source,
            raw_data=raw_data,
        )
        self.session.add(raw)
        self.session.flush()
        return raw

    async def save_raw_async(
        self, batch_id: str, source: str, raw_data: dict[str, Any]
    ) -> JobRaw:
        """
        保存原始数据（异步）。

        Args:
            batch_id: 批次ID
            source: 数据来源
            raw_data: 原始数据

        Returns:
            JobRaw: 保存后的原始数据记录
        """
        raw = JobRaw(
            batch_id=batch_id,
            source=source,
            raw_data=raw_data,
        )
        self.session.add(raw)
        await self.session.flush()
        return raw

    # ==================== 任务操作 ====================

    def create_task(
        self,
        task_id: str,
        spider_name: str,
        batch_id: str,
        config: Optional[dict[str, Any]] = None,
    ) -> CrawlTask:
        """
        创建爬取任务（同步）。

        Args:
            task_id: 任务ID
            spider_name: 爬虫名称
            batch_id: 批次ID
            config: 任务配置

        Returns:
            CrawlTask: 创建的任务记录
        """
        task = CrawlTask(
            task_id=task_id,
            spider_name=spider_name,
            batch_id=batch_id,
            config=config,
        )
        self.session.add(task)
        self.session.flush()
        return task

    async def create_task_async(
        self,
        task_id: str,
        spider_name: str,
        batch_id: str,
        config: Optional[dict[str, Any]] = None,
    ) -> CrawlTask:
        """
        创建爬取任务（异步）。

        Args:
            task_id: 任务ID
            spider_name: 爬虫名称
            batch_id: 批次ID
            config: 任务配置

        Returns:
            CrawlTask: 创建的任务记录
        """
        task = CrawlTask(
            task_id=task_id,
            spider_name=spider_name,
            batch_id=batch_id,
            config=config,
        )
        self.session.add(task)
        await self.session.flush()
        return task
