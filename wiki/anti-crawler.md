# 反爬策略详解

本文档详细介绍招聘网站的反爬机制及应对策略。

## 反爬策略矩阵

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         反爬策略矩阵                                      │
├──────────────┬───────────────┬───────────────┬───────────────────────────┤
│    策略       │    实现难度   │    有效性     │         说明              │
├──────────────┼───────────────┼───────────────┼───────────────────────────┤
│ UA轮换       │      低       │      中       │ 必须配合其他策略           │
│ Referer伪造  │      低       │      低       │ 基础防护                  │
│ Cookie管理   │      中       │      高       │ 保持登录态，需定期刷新      │
│ 请求延迟     │      低       │      中       │ 随机化，模拟人类行为        │
│ 代理池       │      高       │      高       │ 核心策略，需维护代理质量    │
│ 浏览器模拟   │      高       │      高       │ 终极手段，资源消耗大        │
│ 验证码识别   │      高       │      中       │ OCR/打码平台              │
│ 指纹伪装     │      高       │      高       │ TLS/Canvas/Audio指纹       │
└──────────────┴───────────────┴───────────────┴───────────────────────────┘
```

## 目标网站分析

### 智联招聘 (zhilian.com)

| 特征 | 说明 |
|------|------|
| 反爬等级 | 低 |
| 验证码 | 偶发 |
| 登录要求 | 不强制 |
| 请求频率限制 | 宽松 |
| 建议策略 | UA轮换 + 请求延迟 |

**推荐配置：**

```yaml
anti_crawler:
  ua_rotation: true
  random_delay: true
  fake_referer: true
  cookie_management: false
  proxy_enabled: false
  request_delay:
    min: 1.0
    max: 3.0
```

### 前程无忧 (51job.com)

| 特征 | 说明 |
|------|------|
| 反爬等级 | 中 |
| 验证码 | 频繁 |
| 登录要求 | 部分功能需登录 |
| 请求频率限制 | 中等 |
| 建议策略 | 代理池 + Cookie管理 |

**推荐配置：**

```yaml
anti_crawler:
  ua_rotation: true
  random_delay: true
  fake_referer: true
  cookie_management: true
  proxy_enabled: true
  request_delay:
    min: 2.0
    max: 5.0
```

### Boss直聘 (zhipin.com)

| 特征 | 说明 |
|------|------|
| 反爬等级 | 高 |
| 验证码 | 频繁且复杂 |
| 登录要求 | 强制登录 |
| 请求频率限制 | 严格 |
| 建议策略 | 浏览器模拟 + 代理池 |

**推荐配置：**

```yaml
anti_crawler:
  ua_rotation: true
  random_delay: true
  fake_referer: true
  cookie_management: true
  proxy_enabled: true
  browser_simulation: true
  request_delay:
    min: 3.0
    max: 8.0
```

## 策略实现

### 1. User-Agent 轮换

```python
class UserAgentRotator:
    """UA 轮换器"""

    USER_AGENTS = [
        # Chrome Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

        # Chrome Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

        # Firefox Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0",

        # Edge Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",

        # Safari Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]

    def __init__(self, ua_list: list[str] | None = None):
        self.user_agents = ua_list or self.USER_AGENTS
        self._current_idx = 0

    def get_random(self) -> str:
        """获取随机 UA"""
        return random.choice(self.user_agents)

    def get_next(self) -> str:
        """获取下一个 UA（轮询）"""
        ua = self.user_agents[self._current_idx]
        self._current_idx = (self._current_idx + 1) % len(self.user_agents)
        return ua
```

### 2. 请求延迟随机化

```python
class RandomDelay:
    """随机延迟"""

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        distribution: str = "uniform"
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.distribution = distribution

    async def wait(self) -> float:
        """等待随机时间"""
        if self.distribution == "uniform":
            delay = random.uniform(self.min_delay, self.max_delay)
        elif self.distribution == "exponential":
            # 指数分布，更接近人类行为
            delay = random.expovariate(1 / ((self.min_delay + self.max_delay) / 2))
            delay = max(self.min_delay, min(delay, self.max_delay * 2))
        else:
            delay = self.min_delay

        await asyncio.sleep(delay)
        return delay
```

### 3. Cookie 管理

```python
class CookieManager:
    """Cookie 管理器"""

    def __init__(self, cookie_file: str = "data/cookies.json"):
        self.cookie_file = cookie_file
        self.cookies: dict[str, dict] = {}

    def load(self, domain: str) -> dict:
        """加载 Cookie"""
        if os.path.exists(self.cookie_file):
            with open(self.cookie_file, "r") as f:
                data = json.load(f)
                return data.get(domain, {})
        return {}

    def save(self, domain: str, cookies: dict):
        """保存 Cookie"""
        if os.path.exists(self.cookie_file):
            with open(self.cookie_file, "r") as f:
                data = json.load(f)
        else:
            data = {}

        data[domain] = cookies
        with open(self.cookie_file, "w") as f:
            json.dump(data, f)

    def is_expired(self, cookies: dict) -> bool:
        """检查 Cookie 是否过期"""
        # 实现过期检查逻辑
        pass

    async def refresh(self, domain: str):
        """刷新 Cookie"""
        # 实现刷新逻辑
        pass
```

### 4. Referer 伪造

```python
class RefererFaker:
    """Referer 伪造器"""

    REFERERS = {
        "zhilian": [
            "https://www.zhaopin.com/",
            "https://www.zhaopin.com/jobs/",
            "https://sou.zhaopin.com/",
        ],
        "51job": [
            "https://www.51job.com/",
            "https://search.51job.com/",
        ],
        "boss": [
            "https://www.zhipin.com/",
            "https://www.zhipin.com/job_detail/",
        ],
    }

    def get_referer(self, site: str) -> str:
        """获取随机 Referer"""
        referers = self.REFERERS.get(site, [])
        if referers:
            return random.choice(referers)
        return ""
```

### 5. 代理池策略

```python
class ProxyStrategy:
    """代理策略"""

    def __init__(self, proxy_pool: ProxyPool):
        self.pool = proxy_pool
        self.banned_proxies: set[str] = set()

    async def get_proxy(self, site: str) -> ProxyInfo | None:
        """获取可用代理"""
        proxy = await self.pool.get()

        # 检查是否被封禁
        while proxy and proxy.url in self.banned_proxies:
            proxy = await self.pool.get()

        return proxy

    def mark_banned(self, proxy: ProxyInfo):
        """标记被封禁的代理"""
        self.banned_proxies.add(proxy.url)

    async def handle_ban(self, proxy: ProxyInfo, response_status: int):
        """处理被封情况"""
        if response_status == 403:
            self.mark_banned(proxy)
            await self.pool.record_failure(proxy)

            # 增加等待时间
            await asyncio.sleep(60)
```

### 6. 浏览器模拟

```python
from DrissionPage import ChromiumPage

class BrowserSimulator:
    """浏览器模拟器"""

    def __init__(self):
        self.page: ChromiumPage | None = None

    async def start(self):
        """启动浏览器"""
        self.page = ChromiumPage()

        # 设置反检测
        self.page.set.evasions([
            "webdriver",
            "chrome",
            "permissions",
            "plugins",
            "languages",
        ])

    async def goto(self, url: str) -> str:
        """访问页面"""
        self.page.get(url)

        # 等待页面加载
        self.page.wait.load_start()

        # 随机滚动模拟人类行为
        await self._random_scroll()

        return self.page.html

    async def _random_scroll(self):
        """随机滚动"""
        for _ in range(random.randint(2, 5)):
            scroll_distance = random.randint(200, 500)
            self.page.scroll.down(scroll_distance)
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def close(self):
        """关闭浏览器"""
        if self.page:
            self.page.quit()
```

### 7. 验证码处理

```python
class CaptchaHandler:
    """验证码处理器"""

    def __init__(self, ocr_type: str = "local"):
        self.ocr_type = ocr_type

    async def recognize(self, image_data: bytes) -> str:
        """识别验证码"""
        if self.ocr_type == "local":
            return await self._local_ocr(image_data)
        else:
            return await self._third_party_ocr(image_data)

    async def _local_ocr(self, image_data: bytes) -> str:
        """本地 OCR 识别"""
        import ddddocr

        ocr = ddddocr.DdddOcr()
        return ocr.classification(image_data)

    async def _third_party_ocr(self, image_data: bytes) -> str:
        """第三方打码平台"""
        # 实现第三方 API 调用
        pass

    async def handle_slider(self, page, slider_element):
        """处理滑块验证码"""
        # 实现滑块验证码处理
        pass
```

### 8. 指纹伪装

```python
class FingerprintSpoofer:
    """浏览器指纹伪装"""

    SPOOF_SCRIPTS = [
        # 伪装 WebDriver
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",

        # 伪装 plugins
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",

        # 伪装 languages
        "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});",

        # 伪装 platform
        "Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});",

        # 伪装 canvas 指纹
        """
        const originalGetContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type) {
            if (type === '2d') {
                const context = originalGetContext.call(this, type);
                const originalGetImageData = context.getImageData;
                context.getImageData = function(x, y, w, h) {
                    const imageData = originalGetImageData.call(this, x, y, w, h);
                    // 添加噪声
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += Math.random() * 2 - 1;
                    }
                    return imageData;
                };
                return context;
            }
            return originalGetContext.call(this, type);
        };
        """,
    ]

    def inject_scripts(self, page):
        """注入伪装脚本"""
        for script in self.SPOOF_SCRIPTS:
            page.run_js(script)
```

## 综合防护策略

### AntiCrawlerMiddleware

```python
class AntiCrawlerMiddleware:
    """反爬中间件"""

    def __init__(self, config: dict):
        self.config = config
        self.ua_rotator = UserAgentRotator()
        self.delay = RandomDelay(
            min_delay=config.get("delay_min", 1.0),
            max_delay=config.get("delay_max", 3.0),
        )
        self.cookie_manager = CookieManager()
        self.referer_faker = RefererFaker()
        self.proxy_strategy: ProxyStrategy | None = None

    async def before_request(self, request: Request) -> Request:
        """请求前处理"""
        # 1. 设置 UA
        request.headers["User-Agent"] = self.ua_rotator.get_random()

        # 2. 设置 Referer
        if self.config.get("fake_referer"):
            request.headers["Referer"] = self.referer_faker.get_referer(
                self.config.get("site", "")
            )

        # 3. 加载 Cookie
        if self.config.get("cookie_management"):
            cookies = self.cookie_manager.load(request.url.host)
            request.cookies.update(cookies)

        # 4. 设置代理
        if self.config.get("proxy_enabled") and self.proxy_strategy:
            proxy = await self.proxy_strategy.get_proxy(self.config.get("site", ""))
            if proxy:
                request.proxy = proxy.url

        # 5. 随机延迟
        if self.config.get("random_delay"):
            await self.delay.wait()

        return request

    async def after_response(self, response: Response) -> Response:
        """响应后处理"""
        # 1. 保存 Cookie
        if self.config.get("cookie_management"):
            self.cookie_manager.save(
                response.url.host,
                dict(response.cookies)
            )

        # 2. 处理被封情况
        if response.status_code == 403:
            await self._handle_ban(response)

        # 3. 处理验证码
        if self._is_captcha_page(response.text):
            await self._handle_captcha(response)

        return response

    async def _handle_ban(self, response: Response):
        """处理被封"""
        logger.warning(f"IP被封: {response.url}")
        # 实现解封逻辑

    def _is_captcha_page(self, html: str) -> bool:
        """检测验证码页面"""
        captcha_indicators = ["验证码", "captcha", "verify"]
        return any(indicator in html.lower() for indicator in captcha_indicators)

    async def _handle_captcha(self, response: Response):
        """处理验证码"""
        # 实现验证码处理逻辑
        pass
```

## 最佳实践

### 1. 策略选择

根据目标网站选择合适的策略组合：

```python
# 简单网站
config = {
    "ua_rotation": True,
    "random_delay": True,
}

# 中等网站
config = {
    "ua_rotation": True,
    "random_delay": True,
    "fake_referer": True,
    "cookie_management": True,
}

# 严格网站
config = {
    "ua_rotation": True,
    "random_delay": True,
    "fake_referer": True,
    "cookie_management": True,
    "proxy_enabled": True,
    "browser_simulation": True,
}
```

### 2. 频率控制

```python
# 根据时间段调整频率
def get_delay_by_time() -> tuple[float, float]:
    hour = datetime.now().hour
    if 9 <= hour <= 18:  # 工作时间
        return (2.0, 5.0)
    else:  # 非工作时间
        return (1.0, 3.0)
```

### 3. 错误恢复

```python
async def crawl_with_retry(url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = await fetch(url)
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                # 换代理
                await switch_proxy()
            elif response.status_code == 429:
                # 等待后重试
                await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2 ** attempt)  # 指数退避

    raise MaxRetriesExceeded()
```

### 4. 监控告警

```python
# 监控被封情况
async def monitor_ban_rate():
    total = metrics.get_counter("spider_requests_total")
    banned = metrics.get_counter("spider_banned_total")

    if total > 100 and banned / total > 0.1:
        send_alert("封禁率超过 10%，请检查代理质量")
```
