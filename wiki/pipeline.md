# 数据管道 (Pipeline)

数据管道负责对爬取的原始数据进行处理，包括解析、校验、去重和增强等步骤。

## 管道架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据管道 (Pipeline)                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Parser  │ → │ Validator│ → │ Deduper  │ → │ Enricher │    │
│  │  (解析)   │   │  (校验)   │   │  (去重)   │   │  (增强)   │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       ↓              ↓              ↓              ↓           │
│  提取结构化数据   验证数据完整性   消除重复数据   补充额外信息     │
└─────────────────────────────────────────────────────────────────┘
```

## 管道基础

### PipelineStage - 管道阶段基类

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class PipelineStage(ABC):
    """管道阶段抽象基类"""

    @abstractmethod
    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """处理数据项"""
        pass
```

### Pipeline - 管道容器

```python
from job_spider.pipeline.base import Pipeline, PipelineContext

# 创建管道
pipeline = Pipeline()

# 添加处理阶段
pipeline.add_stage(ParserStage())
pipeline.add_stage(ValidatorStage())
pipeline.add_stage(DeduperStage())
pipeline.add_stage(EnricherStage())

# 执行管道
ctx = PipelineContext(task_id="task_001", spider_name="zhilian")
async for item in pipeline.process(raw_items, ctx):
    print(item)
```

## 解析器 (Parser)

### 功能

- 提取结构化数据
- 转换数据格式
- 解析薪资、日期等字段

### 示例实现

```python
from job_spider.pipeline.parser import ParserStage

class SalaryParserStage(ParserStage):
    """薪资解析器"""

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            # 解析薪资字符串 "15-25K" -> (15000, 25000)
            if "salary_raw" in item:
                min_sal, max_sal = self._parse_salary(item["salary_raw"])
                item["salary_min"] = min_sal
                item["salary_max"] = max_sal
                item["salary_avg"] = (min_sal + max_sal) / 2
            yield item

    def _parse_salary(self, salary_str: str) -> tuple[int, int]:
        """解析薪资字符串"""
        import re

        # 匹配 "15-25K"、"15K-25K"、"15-25k" 等格式
        match = re.search(r"(\d+)[kK]?[-~至](\d+)[kK]?", salary_str)
        if match:
            min_val = int(match.group(1)) * 1000
            max_val = int(match.group(2)) * 1000
            return min_val, max_val

        # 匹配 "15K" 单个值
        match = re.search(r"(\d+)[kK]", salary_str)
        if match:
            val = int(match.group(1)) * 1000
            return val, val

        return 0, 0
```

### 日期解析

```python
class DateParserStage(ParserStage):
    """日期解析器"""

    DATE_PATTERNS = [
        ("%Y-%m-%d", None),
        ("%Y/%m/%d", None),
        ("%m-%d", lambda d: f"2024-{d}"),  # 补全年份
    ]

    def _parse_date(self, date_str: str) -> datetime | None:
        for fmt, transform in self.DATE_PATTERNS:
            try:
                if transform:
                    date_str = transform(date_str)
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
```

## 校验器 (Validator)

### 功能

- 验证必填字段
- 验证数据格式
- 过滤无效数据

### 示例实现

```python
from job_spider.pipeline.validator import ValidatorStage

class JobValidatorStage(ValidatorStage):
    """职位数据校验器"""

    # 必填字段
    REQUIRED_FIELDS = ["title", "company", "url", "source"]

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            if self._validate(item):
                yield item
            else:
                ctx.metrics["rejected_count"] = ctx.metrics.get("rejected_count", 0) + 1

    def _validate(self, item: dict) -> bool:
        # 检查必填字段
        for field in self.REQUIRED_FIELDS:
            if not item.get(field):
                return False

        # 检查 URL 格式
        url = item.get("url", "")
        if not url.startswith("http"):
            return False

        # 检查薪资范围
        min_sal = item.get("salary_min")
        max_sal = item.get("salary_max")
        if min_sal and max_sal and min_sal > max_sal:
            return False

        return True
```

### 使用 Pydantic 校验

```python
from pydantic import BaseModel, Field, field_validator

class JobItemSchema(BaseModel):
    """职位数据校验模型"""

    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    url: str = Field(pattern=r"^https?://")
    source: str = Field(min_length=1, max_length=50)

    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v, info):
        min_sal = info.data.get("salary_min")
        if v is not None and min_sal is not None and v < min_sal:
            raise ValueError("最高薪资不能小于最低薪资")
        return v

class PydanticValidatorStage(ValidatorStage):
    """基于 Pydantic 的校验器"""

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            try:
                validated = JobItemSchema(**item)
                yield validated.model_dump()
            except ValidationError as e:
                logger.warning(f"Validation failed: {e}")
```

## 去重器 (Deduper)

### 功能

- 基于 job_id 去重
- 基于内容哈希去重
- 支持多种去重策略

### 示例实现

```python
from job_spider.pipeline.deduper import DeduperStage

class JobDeduperStage(DeduperStage):
    """职位去重器"""

    def __init__(self):
        self._seen_ids: set[str] = set()
        self._seen_hashes: set[str] = set()

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            # 基于 job_id 去重
            job_id = item.get("job_id")
            if job_id and job_id in self._seen_ids:
                continue

            # 基于内容哈希去重
            content_hash = self._hash_item(item)
            if content_hash in self._seen_hashes:
                continue

            # 记录已见
            if job_id:
                self._seen_ids.add(job_id)
            self._seen_hashes.add(content_hash)

            yield item

    def _hash_item(self, item: dict) -> str:
        """计算内容哈希"""
        import hashlib
        content = f"{item.get('title')}|{item.get('company')}|{item.get('location')}"
        return hashlib.md5(content.encode()).hexdigest()
```

### 布隆过滤器去重

```python
from pybloom_live import ScalableBloomFilter

class BloomFilterDeduper(DeduperStage):
    """使用布隆过滤器去重（适合大数据量）"""

    def __init__(self):
        self._bloom = ScalableBloomFilter(
            initial_capacity=100000,
            error_rate=0.001
        )

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            key = item.get("job_id") or self._hash_item(item)
            if key in self._bloom:
                continue
            self._bloom.add(key)
            yield item
```

## 增强器 (Enricher)

### 功能

- 补充公司信息
- 标准化地点
- 提取技能标签

### 示例实现

```python
class JobEnricherStage(PipelineStage):
    """职位数据增强器"""

    # 城市别名映射
    CITY_ALIASES = {
        "杭州": "杭州",
        "杭州市": "杭州",
        "Hangzhou": "杭州",
        "深圳": "深圳",
        "深圳市": "深圳",
        "Shenzhen": "深圳",
    }

    # 技能关键词
    SKILL_KEYWORDS = [
        "Python", "Java", "JavaScript", "Go", "Rust",
        "React", "Vue", "Angular", "Node.js",
        "MySQL", "PostgreSQL", "MongoDB", "Redis",
        "Docker", "Kubernetes", "AWS", "GCP",
        "机器学习", "深度学习", "NLP", "CV",
    ]

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        async for item in items:
            # 标准化城市名
            item["city_normalized"] = self._normalize_city(item.get("location", ""))

            # 提取技能标签
            item["skills"] = self._extract_skills(item.get("description", ""))

            # 计算薪资等级
            avg_sal = item.get("salary_avg", 0)
            item["salary_level"] = self._get_salary_level(avg_sal)

            yield item

    def _normalize_city(self, location: str) -> str:
        """标准化城市名"""
        for alias, standard in self.CITY_ALIASES.items():
            if alias in location:
                return standard
        return location.split("-")[0] if "-" in location else location

    def _extract_skills(self, description: str) -> list[str]:
        """提取技能标签"""
        skills = []
        for skill in self.SKILL_KEYWORDS:
            if skill.lower() in description.lower():
                skills.append(skill)
        return skills

    def _get_salary_level(self, avg_salary: int) -> str:
        """计算薪资等级"""
        if avg_salary < 10000:
            return "entry"
        elif avg_salary < 20000:
            return "junior"
        elif avg_salary < 35000:
            return "mid"
        elif avg_salary < 50000:
            return "senior"
        else:
            return "expert"
```

## 完整管道示例

```python
async def build_pipeline() -> Pipeline:
    """构建完整的数据处理管道"""

    pipeline = Pipeline()

    # 1. 解析阶段
    pipeline.add_stage(SalaryParserStage())
    pipeline.add_stage(DateParserStage())

    # 2. 校验阶段
    pipeline.add_stage(JobValidatorStage())

    # 3. 去重阶段
    pipeline.add_stage(JobDeduperStage())

    # 4. 增强阶段
    pipeline.add_stage(JobEnricherStage())

    return pipeline

async def process_jobs(raw_items: list[dict]):
    """处理职位数据"""
    pipeline = await build_pipeline()
    ctx = PipelineContext(task_id="task_001", spider_name="zhilian")

    processed_items = []
    async for item in pipeline.process(iter_async(raw_items), ctx):
        processed_items.append(item)

    return processed_items
```

## 管道监控

```python
class MonitoredPipelineStage(PipelineStage):
    """带监控的管道阶段"""

    def __init__(self, stage: PipelineStage, name: str):
        self.stage = stage
        self.name = name
        self.processed_count = 0
        self.error_count = 0
        self.total_time = 0.0

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        import time

        async for item in items:
            start = time.monotonic()
            try:
                async for result in self.stage.process(iter_async([item]), ctx):
                    self.processed_count += 1
                    yield result
            except Exception as e:
                self.error_count += 1
                logger.error(f"Pipeline stage {self.name} error: {e}")
            finally:
                self.total_time += time.monotonic() - start
```

## 最佳实践

### 1. 阶段职责单一

每个阶段只做一件事，便于测试和维护。

### 2. 异步处理

使用异步迭代器处理大量数据，避免内存溢出。

### 3. 错误处理

```python
async def process(
    self,
    items: AsyncIterator[dict],
    ctx: PipelineContext
) -> AsyncIterator[dict]:
    async for item in items:
        try:
            # 处理逻辑
            yield processed_item
        except Exception as e:
            logger.warning(f"Item processing failed: {e}")
            ctx.metrics["errors"] = ctx.metrics.get("errors", 0) + 1
            # 选择：跳过或重新抛出
```

### 4. 可配置性

```python
class DeduperStage(PipelineStage):
    def __init__(
        self,
        use_bloom_filter: bool = False,
        initial_capacity: int = 100000
    ):
        if use_bloom_filter:
            self._seen = ScalableBloomFilter(initial_capacity)
        else:
            self._seen = set()
```
