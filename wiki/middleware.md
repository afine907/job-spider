# 中间件系统

Job Spider 提供了完善的中间件系统，用于处理爬虫请求过程中的各种问题，包括代理管理、限流、熔断和重试等。

## 中间件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        中间件层 (Middleware Layer)                │
├─────────────────────────────────────────────────────────────────┤
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ Proxy Pool │ │Rate Limiter│ │CircuitBreak│ │   Retry    │   │
│  │  (代理池)   │ │  (限流器)   │ │  (熔断器)   │ │  (重试)    │   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘   │
│  ┌────────────┐ ┌────────────┐                                   │
│  │UA Rotation │ │   Cookie   │                                   │
│  │ (UA轮换)   │ │  (Cookie)  │                                   │
│  └────────────┘ └────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 代理池 (Proxy Pool)

### 功能特性

- 支持从文件、环境变量、列表加载代理
- 代理健康检查
- 优先级排序
- 多种选择策略（随机、优先级、最快）
- 失效代理自动移除

### 基本使用

```python
from job_spider.middleware.proxy import (
    ProxyPool,
    ProxyInfo,
    ProxyProtocol,
    ProxyPoolConfig,
)

# 创建代理池
pool = ProxyPool()

# 添加代理
pool.add(
    url="http://user:pass@proxy.example.com:8080",
    protocol=ProxyProtocol.HTTP,
    priority=10,  # 数值越小优先级越高
)

# 批量添加
proxy_list = [
    "http://proxy1:8080",
    "http://proxy2:8080",
    "socks5://proxy3:1080",
]
pool.load_from_list(proxy_list)

# 从文件加载
pool.load_from_file("proxies.txt")

# 从环境变量加载
pool.load_from_env("HTTP_PROXY")
```

### 获取代理

```python
# 获取可用代理
proxy = await pool.get()
if proxy:
    print(f"Using proxy: {proxy.address}")
    print(f"Priority: {proxy.priority}")
    print(f"Avg response time: {proxy.avg_response_time}s")

# 记录使用结果
await pool.record_success(proxy, response_time=0.5)
# 或
await pool.record_failure(proxy)
```

### 健康检查

```python
# 检查单个代理
is_healthy = await pool.check_health(proxy)

# 检查所有代理
results = await pool.check_all_health()
print(f"Healthy: {results['healthy']}, Unhealthy: {results['unhealthy']}")

# 启动后台健康检查
pool.start_health_check_loop()

# 停止后台检查
await pool.stop_health_check_loop()
```

### 配置选项

```python
config = ProxyPoolConfig(
    health_check_interval=300.0,    # 健康检查间隔（秒）
    max_fail_count=3,               # 最大失败次数
    retry_cooldown=60.0,            # 失败后冷却时间
    enable_health_check=True,       # 启用健康检查
    health_check_timeout=10.0,      # 检查超时时间
    selection_strategy="priority",  # 选择策略：random/priority/fastest
)

pool = ProxyPool(config=config)
```

### 统计信息

```python
stats = pool.get_stats()
# {
#     "total": 10,
#     "healthy": 8,
#     "enabled": 10,
#     "unhealthy": 2,
#     "proxies": [...]
# }
```

## 限流器 (Rate Limiter)

### 功能特性

- 基于令牌桶算法
- 支持平滑限流
- 支持突发流量

### 基本使用

```python
from job_spider.middleware.rate_limiter import RateLimiter

# 创建限流器：每秒最多 10 个请求
limiter = RateLimiter(rate=10, capacity=10)

# 检查是否允许请求
if limiter.acquire():
    # 允许请求
    pass
else:
    # 被限流，等待
    wait_time = limiter.get_wait_time()
    await asyncio.sleep(wait_time)
```

### 异步限流

```python
from job_spider.middleware.rate_limiter import AsyncRateLimiter

limiter = AsyncRateLimiter(rate=10, capacity=20)

async def make_request():
    async with limiter:
        # 自动等待获取令牌
        response = await client.get(url)
    return response
```

## 熔断器 (Circuit Breaker)

### 状态模型

```
         失败次数达到阈值
    ┌──────────────────────┐
    │                      │
    ▼                      │
┌────────┐            ┌────────┐
│ CLOSED │ ──────────▶│  OPEN  │
└────────┘            └────────┘
    ▲                      │
    │                      │ 超时后
    │ 成功次数达到阈值      ▼
    │                 ┌───────────┐
    └─────────────────│ HALF_OPEN │
                      └───────────┘
```

### 三种状态

| 状态 | 说明 |
|------|------|
| CLOSED | 正常状态，允许请求通过 |
| OPEN | 熔断状态，拒绝所有请求 |
| HALF_OPEN | 半开状态，允许部分请求测试恢复 |

### 基本使用

```python
from job_spider.middleware.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerError,
)

# 创建熔断器
breaker = CircuitBreaker(
    name="api_breaker",
    failure_threshold=5,      # 失败 5 次后熔断
    success_threshold=3,      # 成功 3 次后恢复
    recovery_timeout=30.0,    # 熔断持续 30 秒
)

# 方式一：上下文管理器
try:
    async with breaker:
        result = await api_call()
except CircuitBreakerError:
    print("熔断器打开，服务不可用")

# 方式二：call 方法
try:
    result = await breaker.call(api_call)
except CircuitBreakerError:
    print("服务熔断")
```

### 状态查询

```python
# 检查状态
if breaker.is_open:
    print("熔断器打开")
elif breaker.is_half_open:
    print("熔断器半开")
elif breaker.is_closed:
    print("熔断器关闭")

# 获取统计信息
stats = breaker.stats
print(f"Total: {stats.total_calls}")
print(f"Success: {stats.successful_calls}")
print(f"Failed: {stats.failed_calls}")
print(f"Rejected: {stats.rejected_calls}")
```

### 配置选项

```python
from job_spider.middleware.circuit_breaker import CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,          # 失败阈值
    success_threshold=3,          # 成功阈值
    recovery_timeout=30.0,        # 恢复超时
    half_open_max_calls=1,        # 半开状态最大请求数
    failure_rate_threshold=0.5,   # 失败率阈值
    minimum_number_of_calls=10,   # 最小请求数
    sliding_window_size=60.0,     # 滑动窗口大小
)

breaker = CircuitBreaker(config=config)
```

### 状态变化回调

```python
def on_state_change(old_state: CircuitState, new_state: CircuitState):
    print(f"State changed: {old_state.value} -> {new_state.value}")
    # 发送告警通知...

breaker.on_state_change(on_state_change)
```

### 手动控制

```python
# 重置熔断器
breaker.reset()

# 强制打开
breaker.force_open()

# 强制关闭
breaker.force_close()
```

## 重试管理 (Retry)

### 基本使用

```python
from job_spider.middleware.retry import RetryManager, RetryConfig

config = RetryConfig(
    max_retries=3,              # 最大重试次数
    base_delay=1.0,             # 基础延迟
    max_delay=60.0,             # 最大延迟
    exponential_base=2,         # 指数基数
    jitter=True,                # 添加随机抖动
    retryable_exceptions=[      # 可重试的异常
        httpx.TimeoutException,
        httpx.NetworkError,
    ],
)

retry_manager = RetryManager(config=config)

@retry_manager.retry
async def fetch_url(url: str):
    async with httpx.AsyncClient() as client:
        return await client.get(url)
```

### 重试策略

```python
# 指数退避
# 第1次: 1s
# 第2次: 2s
# 第3次: 4s
# ...

# 线性退避
# 第1次: 1s
# 第2次: 2s
# 第3次: 3s
# ...

# 固定延迟
# 第1次: 1s
# 第2次: 1s
# 第3次: 1s
# ...
```

## User-Agent 轮换

```python
from job_spider.middleware.user_agent import UserAgentPool

# 创建 UA 池
ua_pool = UserAgentPool()

# 获取随机 UA
ua = ua_pool.get_random()
# "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"

# 获取特定类型 UA
ua = ua_pool.get_by_type("chrome")
ua = ua_pool.get_by_type("firefox")
ua = ua_pool.get_by_os("windows")
ua = ua_pool.get_by_os("macos")
```

## 中间件组合使用

```python
class ResilientHttpClient:
    """具有完整容错能力的 HTTP 客户端"""

    def __init__(self):
        self.proxy_pool = ProxyPool()
        self.breaker = CircuitBreaker(failure_threshold=5)
        self.limiter = AsyncRateLimiter(rate=10)
        self.retry = RetryManager(max_retries=3)

    async def request(self, url: str) -> Response:
        # 1. 熔断保护
        async with self.breaker:
            # 2. 限流
            async with self.limiter:
                # 3. 获取代理
                proxy = await self.proxy_pool.get()

                try:
                    # 4. 发送请求（带重试）
                    return await self.retry.execute(
                        self._do_request,
                        url,
                        proxy
                    )
                except Exception as e:
                    # 记录代理失败
                    if proxy:
                        await self.proxy_pool.record_failure(proxy)
                    raise

    async def _do_request(self, url: str, proxy: ProxyInfo) -> Response:
        async with httpx.AsyncClient(proxy=proxy.url) as client:
            return await client.get(url)
```

## 最佳实践

### 1. 代理池预热

```python
async def warmup_proxy_pool(pool: ProxyPool):
    """启动时检查代理健康状态"""
    results = await pool.check_all_health()
    print(f"Healthy proxies: {results['healthy']}/{pool.count}")
```

### 2. 熔断器告警

```python
def setup_breaker_alerts(breaker: CircuitBreaker):
    """设置熔断器告警"""
    def on_state_change(old, new):
        if new == CircuitState.OPEN:
            send_alert(f"熔断器 {breaker.name} 打开！")
    breaker.on_state_change(on_state_change)
```

### 3. 限流器配置

```python
# 根据目标网站调整限流参数
# 简单网站
limiter = AsyncRateLimiter(rate=5, capacity=10)

# 严格网站
limiter = AsyncRateLimiter(rate=1, capacity=3)
```
