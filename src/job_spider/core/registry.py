"""
爬虫注册中心模块。

实现爬虫的注册、发现和管理。
"""

from typing import Callable, TypeVar, Any
import structlog

from job_spider.spiders.base import SpiderContext

logger = structlog.get_logger(__name__)

__all__ = ['BaseSpider', 'SpiderRegistry', 'register_spider', '_default_registry', 'registry']

# 爬虫类型变量
T = TypeVar("T", bound="BaseSpider")


class BaseSpider:
    """
    爬虫基类。

    所有爬虫都应继承此类并实现 run 方法。

    Example:
        >>> class MySpider(BaseSpider):
        ...     name = "my_spider"
        ...
        ...     async def run(self, ctx: SpiderContext) -> list[dict]:
        ...         return [{"title": "Python工程师", "company": "ABC公司"}]
    """

    name: str = "base_spider"
    description: str = "爬虫基类"

    async def run(self, ctx: SpiderContext) -> list[dict[str, Any]]:
        """
        执行爬虫逻辑。

        Args:
            ctx: 爬虫上下文

        Returns:
            list[dict[str, Any]]: 爬取的数据列表

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError(f"爬虫 {self.name} 未实现 run 方法")

    async def setup(self, ctx: SpiderContext) -> None:
        """
        爬虫初始化钩子。

        在 run 之前调用，用于准备资源。

        Args:
            ctx: 爬虫上下文
        """
        pass

    async def teardown(self, ctx: SpiderContext) -> None:
        """
        爬虫清理钩子。

        在 run 之后调用，用于清理资源。

        Args:
            ctx: 爬虫上下文
        """
        pass


class SpiderRegistry:
    """
    爬虫注册中心。

    管理所有已注册的爬虫，支持通过名称获取爬虫类。

    Example:
        >>> registry = SpiderRegistry()
        >>>
        >>> @registry.register("boss")
        ... class BossSpider(BaseSpider):
        ...     name = "boss"
        ...
        >>> spider_cls = registry.get("boss")
        >>> print(spider_cls.name)
        'boss'
        >>>
        >>> all_spiders = registry.list_all()
        >>> print(list(all_spiders.keys()))
        ['boss']
    """

    def __init__(self) -> None:
        """初始化注册中心。"""
        self._spiders: dict[str, type[BaseSpider]] = {}

    def register(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[type[T]], type[T]]:
        """
        注册爬虫的装饰器。

        Args:
            name: 爬虫名称，为 None 时使用类属性 name
            description: 爬虫描述

        Returns:
            Callable: 装饰器函数

        Example:
            >>> @registry.register("boss", description="Boss直聘爬虫")
            ... class BossSpider(BaseSpider):
            ...     pass

            >>> @registry.register()  # 使用类属性 name
            ... class LagouSpider(BaseSpider):
            ...     name = "lagou"
        """

        def decorator(cls: type[T]) -> type[T]:
            spider_name = name or cls.name
            if description:
                cls.description = description

            if spider_name in self._spiders:
                logger.warning(
                    "爬虫名称冲突，将覆盖已有爬虫",
                    spider_name=spider_name,
                    old_spider=self._spiders[spider_name].__name__,
                    new_spider=cls.__name__,
                )

            self._spiders[spider_name] = cls
            logger.info("爬虫注册成功", spider_name=spider_name, spider_cls=cls.__name__)

            return cls

        return decorator

    def get(self, name: str) -> type[BaseSpider] | None:
        """
        获取指定名称的爬虫类。

        Args:
            name: 爬虫名称

        Returns:
            type[BaseSpider] | None: 爬虫类，不存在时返回 None

        Example:
            >>> spider_cls = registry.get("boss")
            >>> if spider_cls:
            ...     spider = spider_cls()
        """
        spider_cls = self._spiders.get(name)
        if spider_cls is None:
            logger.warning("爬虫不存在", spider_name=name)
        return spider_cls

    def get_or_raise(self, name: str) -> type[BaseSpider]:
        """
        获取指定名称的爬虫类，不存在时抛出异常。

        Args:
            name: 爬虫名称

        Returns:
            type[BaseSpider]: 爬虫类

        Raises:
            KeyError: 爬虫不存在

        Example:
            >>> try:
            ...     spider_cls = registry.get_or_raise("boss")
            ... except KeyError as e:
            ...     print(f"爬虫不存在: {e}")
        """
        spider_cls = self._spiders.get(name)
        if spider_cls is None:
            raise KeyError(f"爬虫 '{name}' 不存在，可用爬虫: {list(self._spiders.keys())}")
        return spider_cls

    def list_all(self) -> dict[str, type[BaseSpider]]:
        """
        获取所有已注册的爬虫。

        Returns:
            dict[str, type[BaseSpider]]: 爬虫名称到爬虫类的映射

        Example:
            >>> all_spiders = registry.list_all()
            >>> for name, cls in all_spiders.items():
            ...     print(f"{name}: {cls.description}")
        """
        return self._spiders.copy()

    def list_names(self) -> list[str]:
        """
        获取所有已注册爬虫的名称列表。

        Returns:
            list[str]: 爬虫名称列表

        Example:
            >>> names = registry.list_names()
            >>> print(names)
            ['boss', 'lagou', 'zhilian']
        """
        return list(self._spiders.keys())

    def unregister(self, name: str) -> bool:
        """
        注销指定名称的爬虫。

        Args:
            name: 爬虫名称

        Returns:
            bool: 是否成功注销

        Example:
            >>> if registry.unregister("boss"):
            ...     print("爬虫已注销")
        """
        if name in self._spiders:
            del self._spiders[name]
            logger.info("爬虫已注销", spider_name=name)
            return True
        return False

    def clear(self) -> None:
        """清空所有已注册的爬虫。"""
        self._spiders.clear()
        logger.info("所有爬虫已清空")

    def __contains__(self, name: str) -> bool:
        """检查爬虫是否已注册。"""
        return name in self._spiders

    def __len__(self) -> int:
        """返回已注册爬虫的数量。"""
        return len(self._spiders)


# 全局注册中心实例
_default_registry = SpiderRegistry()

# 别名，便于外部使用
registry = _default_registry


# 便捷装饰器
def register_spider(
    name: str | None = None,
    description: str | None = None,
) -> Callable[[type[T]], type[T]]:
    """
    注册爬虫的便捷装饰器。

    使用全局注册中心注册爬虫。

    Args:
        name: 爬虫名称
        description: 爬虫描述

    Returns:
        Callable: 装饰器函数

    Example:
        >>> @register_spider("boss", description="Boss直聘爬虫")
        ... class BossSpider(BaseSpider):
        ...     name = "boss"
    """
    return _default_registry.register(name, description)
