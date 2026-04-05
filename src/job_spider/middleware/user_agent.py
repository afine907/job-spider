"""
User-Agent 轮换中间件

提供浏览器 User-Agent 的轮换功能，支持桌面端和移动端类型切换。
"""

import random
from typing import Literal, Optional


class UserAgentRotator:
    """
    User-Agent 轮换器

    管理浏览器 User-Agent 列表，支持随机获取和类型切换。

    Attributes:
        desktop_agents: 桌面端 UA 列表
        mobile_agents: 移动端 UA 列表

    Example:
        >>> rotator = UserAgentRotator()
        >>> ua = rotator.get()  # 随机获取 UA
        >>> mobile_ua = rotator.get(device_type='mobile')
    """

    # Chrome 桌面端 User-Agent
    CHROME_DESKTOP = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]

    # Firefox 桌面端 User-Agent
    FIREFOX_DESKTOP = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    ]

    # Edge 桌面端 User-Agent
    EDGE_DESKTOP = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ]

    # Safari 桌面端 User-Agent
    SAFARI_DESKTOP = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ]

    # Chrome 移动端 User-Agent
    CHROME_MOBILE = [
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    ]

    # Safari 移动端 User-Agent (iPhone)
    SAFARI_MOBILE = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    ]

    def __init__(
        self,
        custom_desktop_agents: Optional[list[str]] = None,
        custom_mobile_agents: Optional[list[str]] = None,
    ) -> None:
        """
        初始化 User-Agent 轮换器

        Args:
            custom_desktop_agents: 自定义桌面端 UA 列表，会追加到默认列表
            custom_mobile_agents: 自定义移动端 UA 列表，会追加到默认列表
        """
        # 合并默认和自定义桌面端 UA
        self.desktop_agents = (
            self.CHROME_DESKTOP
            + self.FIREFOX_DESKTOP
            + self.EDGE_DESKTOP
            + self.SAFARI_DESKTOP
        )
        if custom_desktop_agents:
            self.desktop_agents.extend(custom_desktop_agents)

        # 合并默认和自定义移动端 UA
        self.mobile_agents = self.CHROME_MOBILE + self.SAFARI_MOBILE
        if custom_mobile_agents:
            self.mobile_agents.extend(custom_mobile_agents)

    def get(
        self,
        device_type: Literal["desktop", "mobile"] = "desktop",
        browser: Optional[Literal["chrome", "firefox", "edge", "safari"]] = None,
    ) -> str:
        """
        随机获取一个 User-Agent

        Args:
            device_type: 设备类型，'desktop' 或 'mobile'
            browser: 指定浏览器类型，不指定则随机选择

        Returns:
            随机选择的 User-Agent 字符串

        Raises:
            ValueError: 当指定的设备类型无效时
        """
        if device_type == "desktop":
            if browser:
                return self._get_desktop_by_browser(browser)
            return random.choice(self.desktop_agents)
        elif device_type == "mobile":
            if browser:
                return self._get_mobile_by_browser(browser)
            return random.choice(self.mobile_agents)
        else:
            raise ValueError(f"Invalid device_type: {device_type}. Must be 'desktop' or 'mobile'.")

    def _get_desktop_by_browser(
        self, browser: Literal["chrome", "firefox", "edge", "safari"]
    ) -> str:
        """根据浏览器类型获取桌面端 UA"""
        browser_agents = {
            "chrome": self.CHROME_DESKTOP,
            "firefox": self.FIREFOX_DESKTOP,
            "edge": self.EDGE_DESKTOP,
            "safari": self.SAFARI_DESKTOP,
        }
        agents = browser_agents.get(browser, self.desktop_agents)
        return random.choice(agents)

    def _get_mobile_by_browser(
        self, browser: Literal["chrome", "firefox", "edge", "safari"]
    ) -> str:
        """根据浏览器类型获取移动端 UA"""
        browser_agents = {
            "chrome": self.CHROME_MOBILE,
            "safari": self.SAFARI_MOBILE,
        }
        # Firefox 和 Edge 移动端使用 Chrome UA
        if browser in ("firefox", "edge"):
            agents = self.CHROME_MOBILE
        else:
            agents = browser_agents.get(browser, self.mobile_agents)
        return random.choice(agents)

    def get_all(
        self, device_type: Optional[Literal["desktop", "mobile"]] = None
    ) -> list[str]:
        """
        获取所有 User-Agent 列表

        Args:
            device_type: 设备类型，不指定则返回全部

        Returns:
            User-Agent 列表
        """
        if device_type == "desktop":
            return self.desktop_agents.copy()
        elif device_type == "mobile":
            return self.mobile_agents.copy()
        elif device_type is None:
            return self.desktop_agents + self.mobile_agents
        else:
            raise ValueError(f"Invalid device_type: {device_type}")

    def count(self, device_type: Optional[Literal["desktop", "mobile"]] = None) -> int:
        """
        获取 User-Agent 数量

        Args:
            device_type: 设备类型，不指定则返回总数

        Returns:
            User-Agent 数量
        """
        if device_type == "desktop":
            return len(self.desktop_agents)
        elif device_type == "mobile":
            return len(self.mobile_agents)
        elif device_type is None:
            return len(self.desktop_agents) + len(self.mobile_agents)
        else:
            raise ValueError(f"Invalid device_type: {device_type}")
