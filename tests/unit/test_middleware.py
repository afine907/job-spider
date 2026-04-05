"""Tests for pipeline modules."""

import pytest

from job_spider.pipeline.parser import parse_salary, parse_experience, parse_education
from job_spider.pipeline.validator import ValidateStage, ValidationRule
from job_spider.pipeline.deduper import DedupStage


class TestSalaryParser:
    """Tests for salary parsing."""

    def test_parse_salary_k(self):
        """Test parsing salary with K unit."""
        result = parse_salary("10K-20K")
        assert result == (10000, 20000)

    def test_parse_salary_wan(self):
        """Test parsing salary with 万 unit."""
        result = parse_salary("1万-2万")
        assert result == (10000, 20000)

    def test_parse_salary_empty(self):
        """Test parsing empty salary."""
        result = parse_salary("")
        assert result == (0, 0)

    def test_parse_salary_none(self):
        """Test parsing None salary."""
        result = parse_salary(None)
        assert result == (0, 0)


class TestExperienceParser:
    """Tests for experience parsing."""

    def test_parse_experience_years(self):
        """Test parsing years of experience."""
        assert parse_experience("3-5年") == "3-5年"

    def test_parse_experience_unlimited(self):
        """Test parsing unlimited experience."""
        assert parse_experience("不限") == "不限"

    def test_parse_experience_fresh(self):
        """Test parsing fresh graduate."""
        assert parse_experience("应届生") == "应届生"


class TestEducationParser:
    """Tests for education parsing."""

    def test_parse_education_bachelor(self):
        """Test parsing bachelor degree."""
        assert parse_education("本科") == "本科"

    def test_parse_education_master(self):
        """Test parsing master degree."""
        assert parse_education("硕士") == "硕士"

    def test_parse_education_unlimited(self):
        """Test parsing unlimited education."""
        assert parse_education("不限") == "不限"


class TestValidator:
    """Tests for validation stage."""

    @pytest.mark.asyncio
    async def test_validate_valid_item(self):
        """Test validating a valid item."""
        validator = ValidateStage()

        items = [
            {
                "job_id": "123",
                "title": "Python工程师",
                "company": "测试公司",
                "city": "深圳",
                "url": "https://example.com/job/123",
            }
        ]

        from job_spider.pipeline.base import PipelineContext
        ctx = PipelineContext(task_id="test", spider_name="test")

        async def item_generator():
            for item in items:
                yield item

        results = []
        async for item in validator.process(item_generator(), ctx):
            results.append(item)

        assert len(results) == 1
        assert ctx.metrics.get("valid", 0) == 1

    @pytest.mark.asyncio
    async def test_validate_invalid_item(self):
        """Test validating an invalid item."""
        validator = ValidateStage()

        items = [
            {
                "job_id": "",  # Empty, should fail
                "title": "Python工程师",
                "company": "测试公司",
                "city": "深圳",
                "url": "https://example.com/job/123",
            }
        ]

        from job_spider.pipeline.base import PipelineContext
        ctx = PipelineContext(task_id="test", spider_name="test")

        async def item_generator():
            for item in items:
                yield item

        results = []
        async for item in validator.process(item_generator(), ctx):
            results.append(item)

        assert len(results) == 0
        assert ctx.metrics.get("invalid", 0) == 1


class TestDeduper:
    """Tests for deduplication stage."""

    @pytest.mark.asyncio
    async def test_dedup_unique_items(self):
        """Test deduplicating unique items."""
        deduper = DedupStage(fields=["job_id", "source"])

        items = [
            {"job_id": "1", "source": "zhilian", "title": "Job 1"},
            {"job_id": "2", "source": "zhilian", "title": "Job 2"},
        ]

        from job_spider.pipeline.base import PipelineContext
        ctx = PipelineContext(task_id="test", spider_name="test")

        async def item_generator():
            for item in items:
                yield item

        results = []
        async for item in deduper.process(item_generator(), ctx):
            results.append(item)

        assert len(results) == 2
        assert ctx.metrics.get("unique", 0) == 2

    @pytest.mark.asyncio
    async def test_dedup_duplicate_items(self):
        """Test deduplicating duplicate items."""
        deduper = DedupStage(fields=["job_id", "source"])

        items = [
            {"job_id": "1", "source": "zhilian", "title": "Job 1"},
            {"job_id": "1", "source": "zhilian", "title": "Job 1 Duplicate"},
        ]

        from job_spider.pipeline.base import PipelineContext
        ctx = PipelineContext(task_id="test", spider_name="test")

        async def item_generator():
            for item in items:
                yield item

        results = []
        async for item in deduper.process(item_generator(), ctx):
            results.append(item)

        assert len(results) == 1
        assert ctx.metrics.get("duplicates", 0) == 1
