"""Parser stage for extracting job data from raw responses."""

import re
from typing import AsyncIterator

from .base import PipelineStage, PipelineContext


class ParseStage(PipelineStage):
    """Parse raw HTML/JSON into structured job data."""

    def __init__(self, parser_func: callable = None):
        """Initialize parser stage.

        Args:
            parser_func: Custom parser function (item) -> dict | None
        """
        self.parser_func = parser_func

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """Parse raw items into structured data."""
        async for raw_item in items:
            try:
                if self.parser_func:
                    parsed = self.parser_func(raw_item)
                else:
                    parsed = self._default_parse(raw_item)

                if parsed:
                    yield parsed
                    ctx.metrics["parsed"] = ctx.metrics.get("parsed", 0) + 1
                else:
                    ctx.metrics["parse_failed"] = ctx.metrics.get("parse_failed", 0) + 1

            except Exception as e:
                ctx.metrics["parse_errors"] = ctx.metrics.get("parse_errors", 0) + 1
                continue

    def _default_parse(self, raw: dict) -> dict | None:
        """Default parsing logic."""
        # Basic field extraction - override in subclass or use custom parser
        return raw


def parse_salary(salary_str: str) -> tuple[int, int]:
    """Parse salary string to min and max values.

    Args:
        salary_str: Salary string like "10K-20K" or "1万-2万"

    Returns:
        Tuple of (min_salary, max_salary) in yuan/month

    Examples:
        >>> parse_salary("10K-20K")
        (10000, 20000)
        >>> parse_salary("1万-2万")
        (10000, 20000)
    """
    if not salary_str:
        return (0, 0)

    # Normalize string
    salary_str = salary_str.upper().replace(" ", "")

    # Extract numbers
    numbers = re.findall(r"[\d.]+", salary_str)
    if len(numbers) < 2:
        return (0, 0)

    # Determine unit multiplier
    multiplier = 1
    if "万" in salary_str or "W" in salary_str:
        multiplier = 10000
    elif "K" in salary_str:
        multiplier = 1000

    min_val = float(numbers[0]) * multiplier
    max_val = float(numbers[1]) * multiplier

    return (int(min_val), int(max_val))


def parse_experience(exp_str: str) -> str:
    """Normalize experience requirement string."""
    if not exp_str:
        return "不限"

    exp_str = exp_str.strip()

    # Common patterns
    patterns = {
        r"不限|无需经验": "不限",
        r"应届|实习": "应届生",
        r"1[-年以下]": "1年以下",
        r"1[-~至]3": "1-3年",
        r"3[-~至]5": "3-5年",
        r"5[-~至]10": "5-10年",
        r"10年以上|10\+": "10年以上",
    }

    for pattern, normalized in patterns.items():
        if re.search(pattern, exp_str):
            return normalized

    return exp_str


def parse_education(edu_str: str) -> str:
    """Normalize education requirement string."""
    if not edu_str:
        return "不限"

    edu_str = edu_str.strip()

    patterns = {
        r"不限|无要求": "不限",
        r"大专|专科": "大专",
        r"本科|学士": "本科",
        r"硕士|研究生": "硕士",
        r"博士": "博士",
        r"高中|中专": "高中/中专",
    }

    for pattern, normalized in patterns.items():
        if re.search(pattern, edu_str):
            return normalized

    return edu_str
