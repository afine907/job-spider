"""
配置系统模块。

使用 pydantic-settings 实现类型安全的配置管理。
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """数据库配置。"""

    model_config = SettingsConfigDict(env_prefix="DB_")

    sqlite_path: Path = Field(
        default=Path("data/jobs.db"),
        description="SQLite 数据库文件路径",
    )

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        """确保路径为 Path 对象。"""
        if isinstance(v, str):
            return Path(v)
        return v


class SpiderConfig(BaseSettings):
    """爬虫配置。"""

    model_config = SettingsConfigDict(env_prefix="SPIDER_")

    default_delay: float = Field(
        default=1.0,
        ge=0.0,
        le=60.0,
        description="默认请求延迟（秒）",
    )
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=100,
        description="最大并发数",
    )
    timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="请求超时时间（秒）",
    )
    retry_times: int = Field(
        default=3,
        ge=0,
        le=10,
        description="重试次数",
    )
    retry_delay: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
        description="重试延迟（秒）",
    )
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="请求 User-Agent",
    )


class LogConfig(BaseSettings):
    """日志配置。"""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="日志级别",
    )
    format: Literal["json", "console"] = Field(
        default="console",
        description="日志输出格式",
    )
    output_path: Path | None = Field(
        default=None,
        description="日志文件输出路径，为 None 时仅输出到控制台",
    )
    include_trace: bool = Field(
        default=True,
        description="是否包含追踪信息",
    )

    @field_validator("output_path", mode="before")
    @classmethod
    def validate_output_path(cls, v: str | Path | None) -> Path | None:
        """验证并转换输出路径。"""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return Path(v)
        return v


class Settings(BaseSettings):
    """
    应用程序主配置类。

    支持从环境变量和 .env 文件加载配置。
    所有配置项都可通过环境变量覆盖，格式为 {前缀}_{字段名}。

    Attributes:
        project_name: 项目名称
        version: 项目版本
        debug: 调试模式开关
        database: 数据库配置
        spider: 爬虫配置
        log: 日志配置

    Example:
        >>> settings = Settings()
        >>> print(settings.project_name)
        'job-spider'

        # 从环境变量加载
        # export PROJECT_NAME=my-spider
        # export SPIDER_MAX_CONCURRENT=10
        >>> settings = Settings()
        >>> print(settings.project_name)
        'my-spider'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # 基础配置
    project_name: str = Field(
        default="job-spider",
        description="项目名称",
    )
    version: str = Field(
        default="0.1.0",
        description="项目版本",
    )
    debug: bool = Field(
        default=False,
        description="调试模式",
    )

    # 嵌套配置
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig,
        description="数据库配置",
    )
    spider: SpiderConfig = Field(
        default_factory=SpiderConfig,
        description="爬虫配置",
    )
    log: LogConfig = Field(
        default_factory=LogConfig,
        description="日志配置",
    )


# 全局配置实例，延迟初始化
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    获取配置单例。

    Returns:
        Settings: 配置实例

    Example:
        >>> settings = get_settings()
        >>> print(settings.spider.timeout)
        30.0
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    重新加载配置。

    用于测试或需要热更新配置的场景。

    Returns:
        Settings: 新的配置实例
    """
    global _settings
    _settings = Settings()
    return _settings
