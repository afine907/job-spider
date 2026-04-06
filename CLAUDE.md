# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Job Spider is an enterprise-level recruitment data scraping framework supporting multiple Chinese job platforms (Zhilian, 51job, Boss). It features Playwright-based browser automation, resilient HTTP clients with retry/circuit breaker/rate limiting, and async SQLite storage.

## Commands

```bash
# Run tests
PYTHONPATH=src pytest tests/ -v

# Run single test file
PYTHONPATH=src pytest tests/unit/test_middleware.py -v

# CLI operations
PYTHONPATH=src python main.py init                    # Initialize database
PYTHONPATH=src python main.py list-spiders            # List available spiders
PYTHONPATH=src python main.py crawl <spider> -k "Python" -c "北京" -l 50
PYTHONPATH=src python main.py stats                   # View statistics
PYTHONPATH=src python main.py export -f csv -o output/jobs

# Login helper (for anti-crawler sites)
PYTHONPATH=src python login_helper.py

# Code quality
black src/ && isort src/
```

## Architecture

```
src/job_spider/
├── core/           # SpiderEngine, SpiderContext, SpiderRegistry
├── spiders/        # Spider implementations (inherit from BaseSpider)
├── middleware/     # Resilience: retry, circuit breaker, rate limiter
├── pipeline/       # Data processing: parser, validator, deduper
├── storage/        # Database, repository, exporter
└── observability/  # Metrics, tracing, structured logging
```

### Key Patterns

1. **Spider Registration**: Spiders self-register via `@SpiderRegistry.register` decorator
2. **SpiderContext**: Single source of truth for crawl parameters (keyword, city, limit, trace_id, headers, proxy)
3. **ResilientClient**: Combines retry + circuit breaker + rate limiter in one client
4. **Repository Pattern**: `JobRepository` handles all database operations with async/sync support

### Data Flow

```
Spider.search() → JobItem[] → CrawlResult → main.py saves to DB via JobRepository
```

## Available Spiders

| Spider | Use Case | Notes |
|--------|----------|-------|
| `zhilian-browser` | Zhilian (智联招聘) | Requires login via `login_helper.py` first |
| `51job` | 51job (前程无忧) | Network restrictions may apply |
| `remoteok` | RemoteOK API | Real API, no anti-crawler |
| `mock` | Testing | Generates fake data |

## Anti-Crawler Strategy

For sites with captcha/anti-bot protection:
1. Run `python login_helper.py` to manually login and save browser state
2. Use `zhilian-browser` spider which loads saved cookies
3. State saved to `data/browser_state/*.json`

## Database

- SQLite with async support via aiosqlite
- Connection string: `sqlite+aiosqlite:///data/jobs.db`
- Models in `storage/models.py` (JobRaw, JobProcessed, CrawlTask)
- Repository in `storage/repository.py`

## Important Files

- `spiders/base.py`: BaseSpider, SpiderContext, JobItem, CrawlResult, SpiderRegistry
- `core/engine.py`: SpiderEngine executes spiders with concurrency control
- `middleware/resilience.py`: ResilientClient with retry/circuit breaker/rate limiting
- `storage/models.py`: SQLAlchemy models and Pydantic validation schemas
