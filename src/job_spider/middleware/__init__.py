"""
中间件模块

提供爬虫所需的各类中间件组件：
- UserAgentRotator: User-Agent 轮换
- RateLimiter: 请求限流
- ProxyPool: 代理池管理
- CircuitBreaker: 熔断器
- RetryPolicy: 重试策略
- ResilientClient: 弹性调用客户端（融合重试、熔断、限流）
"""

from job_spider.middleware.user_agent import UserAgentRotator
from job_spider.middleware.rate_limiter import RateLimiter
from job_spider.middleware.proxy import ProxyPool, ProxyInfo
from job_spider.middleware.circuit_breaker import CircuitBreaker, CircuitState
from job_spider.middleware.retry import RetryPolicy, RetryConfig
from job_spider.middleware.resilience import ResilientClient, ResilientClientBuilder

__all__ = [
    "UserAgentRotator",
    "RateLimiter",
    "ProxyPool",
    "ProxyInfo",
    "CircuitBreaker",
    "CircuitState",
    "RetryPolicy",
    "RetryConfig",
    "ResilientClient",
    "ResilientClientBuilder",
]
