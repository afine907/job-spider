"""Validator stage for data quality checks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Any

from .base import PipelineStage, PipelineContext


@dataclass
class ValidationRule:
    """Validation rule definition."""
    field: str
    rule: callable
    message: str
    required: bool = True

    def check(self, item: dict) -> bool:
        """Check if item passes this rule."""
        value = item.get(self.field)

        if value is None or value == "":
            return not self.required

        return self.rule(value)


class ValidateStage(PipelineStage):
    """Validate job data quality."""

    def __init__(self, rules: list[ValidationRule] = None):
        """Initialize validator with rules.

        Args:
            rules: List of validation rules
        """
        self.rules = rules or self._default_rules()

    async def process(
        self,
        items: AsyncIterator[dict],
        ctx: PipelineContext
    ) -> AsyncIterator[dict]:
        """Validate items and yield only valid ones."""
        async for item in items:
            errors = self._validate(item)

            if not errors:
                yield item
                ctx.metrics["valid"] = ctx.metrics.get("valid", 0) + 1
            else:
                ctx.metrics["invalid"] = ctx.metrics.get("invalid", 0) + 1
                ctx.metrics.setdefault("validation_errors", []).extend(errors)

    def _validate(self, item: dict) -> list[str]:
        """Validate item against all rules.

        Returns:
            List of error messages, empty if valid
        """
        errors = []

        for rule in self.rules:
            if not rule.check(item):
                errors.append(f"{rule.field}: {rule.message}")

        return errors

    def _default_rules(self) -> list[ValidationRule]:
        """Default validation rules for job data."""
        return [
            ValidationRule(
                field="job_id",
                rule=lambda v: isinstance(v, str) and len(v) > 0,
                message="职位ID不能为空",
                required=True,
            ),
            ValidationRule(
                field="title",
                rule=lambda v: isinstance(v, str) and len(v) >= 2,
                message="职位名称至少2个字符",
                required=True,
            ),
            ValidationRule(
                field="company",
                rule=lambda v: isinstance(v, str) and len(v) >= 2,
                message="公司名称至少2个字符",
                required=True,
            ),
            ValidationRule(
                field="city",
                rule=lambda v: isinstance(v, str) and len(v) >= 2,
                message="城市名称至少2个字符",
                required=True,
            ),
            ValidationRule(
                field="salary_min",
                rule=lambda v: isinstance(v, (int, float)) and v >= 0,
                message="最低薪资必须为非负数",
                required=False,
            ),
            ValidationRule(
                field="salary_max",
                rule=lambda v: isinstance(v, (int, float)) and v >= 0,
                message="最高薪资必须为非负数",
                required=False,
            ),
            ValidationRule(
                field="url",
                rule=lambda v: isinstance(v, str) and v.startswith("http"),
                message="URL格式不正确",
                required=True,
            ),
        ]


# Common validation rules as factory functions
def required(field: str, message: str = None) -> ValidationRule:
    """Create a required field rule."""
    return ValidationRule(
        field=field,
        rule=lambda v: v is not None and v != "",
        message=message or f"{field}为必填项",
        required=True,
    )


def min_length(field: str, length: int, message: str = None) -> ValidationRule:
    """Create a minimum length rule."""
    return ValidationRule(
        field=field,
        rule=lambda v: isinstance(v, str) and len(v) >= length,
        message=message or f"{field}长度不能少于{length}个字符",
    )


def max_length(field: str, length: int, message: str = None) -> ValidationRule:
    """Create a maximum length rule."""
    return ValidationRule(
        field=field,
        rule=lambda v: not isinstance(v, str) or len(v) <= length,
        message=message or f"{field}长度不能超过{length}个字符",
    )


def range_check(field: str, min_val: Any, max_val: Any, message: str = None) -> ValidationRule:
    """Create a range check rule."""
    return ValidationRule(
        field=field,
        rule=lambda v: v is None or (min_val <= v <= max_val),
        message=message or f"{field}必须在{min_val}和{max_val}之间",
        required=False,
    )
