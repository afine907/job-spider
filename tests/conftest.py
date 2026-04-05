"""Pytest configuration and fixtures."""

import asyncio
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory for tests."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_job_data() -> dict:
    """Sample job data for testing."""
    return {
        "job_id": "JL123456",
        "title": "Python开发工程师",
        "company": "测试科技有限公司",
        "salary_min": 15000,
        "salary_max": 25000,
        "city": "深圳",
        "district": "南山区",
        "experience": "3-5年",
        "education": "本科",
        "source": "zhilian",
        "url": "https://www.zhaopin.com/jobs/JL123456.html",
    }
