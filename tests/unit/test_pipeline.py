"""Tests for middleware modules."""

import pytest

from job_spider.middleware.user_agent import UserAgentRotator
from job_spider.middleware.rate_limiter import RateLimiter
from job_spider.middleware.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError


class TestUserAgentRotator:
    """Tests for User-Agent rotation."""

    def test_get_agent(self):
        """Test getting a User-Agent."""
        rotator = UserAgentRotator()
        ua = rotator.get()

        assert ua is not None
        assert "Mozilla" in ua

    def test_get_agent_by_browser(self):
        """Test getting a User-Agent by browser type."""
        rotator = UserAgentRotator()
        ua = rotator.get(browser="chrome")

        assert ua is not None
        assert "Chrome" in ua

    def test_custom_agents(self):
        """Test using custom User-Agent list."""
        custom = ["CustomAgent/1.0", "CustomAgent/2.0"]
        rotator = UserAgentRotator(custom_desktop_agents=custom)

        ua = rotator.get()
        assert ua is not None
        assert rotator.count() > 0


class TestRateLimiter:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting."""
        limiter = RateLimiter(requests_per_second=10)

        # Should not raise
        await limiter.wait()
        await limiter.wait()

    @pytest.mark.asyncio
    async def test_rate_limiter_reset(self):
        """Test rate limiter reset."""
        limiter = RateLimiter(requests_per_second=1)

        await limiter.wait()
        limiter.reset()

        # Should work after reset
        await limiter.wait()

    @pytest.mark.asyncio
    async def test_rate_limiter_context(self):
        """Test rate limiter as context manager."""
        limiter = RateLimiter(requests_per_second=10)

        async with limiter:
            # Can use as context manager
            pass


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_closed_on_success(self):
        """Test circuit stays closed on success."""
        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def success_func():
            return "ok"

        result = await cb.call(success_func)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)

        async def fail_func():
            raise Exception("fail")

        # First failure
        with pytest.raises(Exception):
            await cb.call(fail_func)

        # Second failure - should open circuit
        with pytest.raises(Exception):
            await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self):
        """Test circuit rejects calls when open."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=10.0)

        async def fail_func():
            raise Exception("fail")

        # Trigger open state
        with pytest.raises(Exception):
            await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN

        # Should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await cb.call(lambda: "ok")


class TestPipeline:
    """Tests for pipeline modules."""

    def test_salary_parser(self):
        """Test salary parsing."""
        from job_spider.pipeline.parser import parse_salary

        # Test K format
        min_sal, max_sal = parse_salary("15-25K")
        assert min_sal == 15000
        assert max_sal == 25000

        # Test 万 format
        min_sal, max_sal = parse_salary("1-2万")
        assert min_sal == 10000
        assert max_sal == 20000

    def test_experience_parser(self):
        """Test experience parsing."""
        from job_spider.pipeline.parser import parse_experience

        # 返回的是字符串而不是元组
        result = parse_experience("3-5年经验")
        assert result is not None
        assert "3" in result or "5" in result

    def test_education_parser(self):
        """Test education parsing."""
        from job_spider.pipeline.parser import parse_education

        edu = parse_education("本科及以上")
        assert edu is not None

        edu = parse_education("大专")
        assert edu is not None
