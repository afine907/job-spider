"""
数据库操作模块

提供数据库连接、会话管理和初始化功能。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from job_spider.storage.models import Base


class Database:
    """
    数据库管理类

    支持同步和异步操作，提供连接池和会话管理。
    """

    def __init__(
        self,
        db_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
    ) -> None:
        """
        初始化数据库连接。

        Args:
            db_url: 数据库连接URL
                - SQLite: sqlite:///path/to/db.sqlite 或 sqlite+aiosqlite:///path/to/db.sqlite
                - MySQL: mysql+pymysql://user:pass@host/db 或 mysql+aiomysql://user:pass@host/db
                - PostgreSQL: postgresql+psycopg2://user:pass@host/db 或 postgresql+asyncpg://user:pass@host/db
            echo: 是否打印SQL语句
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            pool_timeout: 连接超时时间(秒)
            pool_recycle: 连接回收时间(秒)
        """
        self.db_url = db_url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle

        # 延迟初始化
        self._sync_engine = None
        self._async_engine = None
        self._sync_session_factory = None
        self._async_session_factory = None

    @property
    def sync_engine(self):
        """获取同步引擎（延迟初始化）"""
        if self._sync_engine is None:
            # 对于SQLite，使用特殊的配置
            if self.db_url.startswith("sqlite"):
                self._sync_engine = create_engine(
                    self.db_url,
                    echo=self.echo,
                    connect_args={"check_same_thread": False},
                )
                # 启用外键约束（SQLite默认关闭）
                @event.listens_for(self._sync_engine, "connect")
                def set_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()
            else:
                self._sync_engine = create_engine(
                    self.db_url,
                    echo=self.echo,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                )
        return self._sync_engine

    @property
    def async_engine(self) -> AsyncEngine:
        """获取异步引擎（延迟初始化）"""
        if self._async_engine is None:
            # 转换为异步URL
            async_url = self._convert_to_async_url(self.db_url)

            if async_url.startswith("sqlite"):
                self._async_engine = create_async_engine(
                    async_url,
                    echo=self.echo,
                )
            else:
                self._async_engine = create_async_engine(
                    async_url,
                    echo=self.echo,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                )
        return self._async_engine

    def _convert_to_async_url(self, url: str) -> str:
        """
        将同步URL转换为异步URL。

        Args:
            url: 同步数据库URL

        Returns:
            异步数据库URL
        """
        if "+aiosqlite" in url or "+aiomysql" in url or "+asyncpg" in url:
            return url

        if url.startswith("sqlite"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        elif url.startswith("mysql"):
            return url.replace("mysql://", "mysql+aiomysql://")
        elif url.startswith("postgresql"):
            return url.replace("postgresql://", "postgresql+asyncpg://")

        return url

    @property
    def sync_session_factory(self):
        """获取同步会话工厂（延迟初始化）"""
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.sync_engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._sync_session_factory

    @property
    def async_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取异步会话工厂（延迟初始化）"""
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
                class_=AsyncSession,
            )
        return self._async_session_factory

    def init_db(self, create_tables: bool = True) -> None:
        """
        初始化数据库（同步方式）。

        Args:
            create_tables: 是否创建表
        """
        if create_tables:
            Base.metadata.create_all(self.sync_engine)

    async def init_db_async(self, create_tables: bool = True) -> None:
        """
        初始化数据库（异步方式）。

        Args:
            create_tables: 是否创建表
        """
        if create_tables:
            async with self.async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    def get_session(self) -> Generator[Session, None, None]:
        """
        获取同步数据库会话。

        Yields:
            Session: SQLAlchemy会话对象
        """
        session = self.sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def get_session_async(self) -> AsyncGenerator[AsyncSession, None]:
        """
        获取异步数据库会话。

        Yields:
            AsyncSession: SQLAlchemy异步会话对象
        """
        async_session = self.async_session_factory()
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise
        finally:
            await async_session.close()

    def close(self) -> None:
        """关闭同步数据库连接"""
        if self._sync_engine is not None:
            self._sync_engine.dispose()
            self._sync_engine = None
            self._sync_session_factory = None

    async def close_async(self) -> None:
        """关闭异步数据库连接"""
        if self._async_engine is not None:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None

    @classmethod
    def from_path(cls, db_path: str | Path, echo: bool = False) -> "Database":
        """
        从文件路径创建SQLite数据库实例。

        Args:
            db_path: 数据库文件路径
            echo: 是否打印SQL语句

        Returns:
            Database: 数据库实例
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"
        return cls(db_url=db_url, echo=echo)


# 全局数据库实例（可通过配置初始化）
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """
    获取全局数据库实例。

    Returns:
        Database: 数据库实例

    Raises:
        RuntimeError: 如果数据库未初始化
    """
    if _db_instance is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    return _db_instance


def init_database(db_url: str, **kwargs) -> Database:
    """
    初始化全局数据库实例。

    Args:
        db_url: 数据库连接URL
        **kwargs: 其他数据库配置参数

    Returns:
        Database: 数据库实例
    """
    global _db_instance
    _db_instance = Database(db_url=db_url, **kwargs)
    return _db_instance


def get_session() -> Generator[Session, None, None]:
    """
    获取数据库会话（使用全局实例）。

    Yields:
        Session: SQLAlchemy会话对象
    """
    yield from get_database().get_session()


@asynccontextmanager
async def get_session_async() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（使用全局实例）。

    Yields:
        AsyncSession: SQLAlchemy异步会话对象
    """
    async with get_database().get_session_async() as session:
        yield session
