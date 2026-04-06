"""Prometheus metrics HTTP server.

Provides a simple HTTP server for exposing Prometheus metrics.
"""

import asyncio
import logging
from typing import Callable

from aiohttp import web

from job_spider.observability.metrics import metrics

logger = logging.getLogger(__name__)


class MetricsServer:
    """HTTP server for Prometheus metrics.

    Example:
        >>> server = MetricsServer(port=8000)
        >>> await server.start()
        >>> # ... later
        >>> await server.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        metrics_path: str = "/metrics",
    ):
        """Initialize metrics server.

        Args:
            host: Server host address
            port: Server port
            metrics_path: Path for metrics endpoint
        """
        self.host = host
        self.port = port
        self.metrics_path = metrics_path
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        """Start the metrics server."""
        self._app = web.Application()
        self._app.router.add_get(self.metrics_path, self._handle_metrics)
        self._app.router.add_get("/health", self._handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        logger.info(f"Metrics server started on http://{self.host}:{self.port}")
        logger.info(f"Metrics available at {self.metrics_path}")

    async def stop(self) -> None:
        """Stop the metrics server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Metrics server stopped")

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handle /metrics request.

        Args:
            request: HTTP request

        Returns:
            HTTP response with Prometheus metrics
        """
        metrics_output = metrics.export_prometheus()
        return web.Response(
            text=metrics_output,
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle /health request.

        Args:
            request: HTTP request

        Returns:
            HTTP response with health status
        """
        return web.json_response({"status": "healthy"})


async def start_metrics_server(
    host: str = "0.0.0.0",
    port: int = 8000,
) -> MetricsServer:
    """Start a metrics server.

    Args:
        host: Server host address
        port: Server port

    Returns:
        MetricsServer instance

    Example:
        >>> server = await start_metrics_server(port=8000)
    """
    server = MetricsServer(host=host, port=port)
    await server.start()
    return server


def run_metrics_server(
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """Run metrics server synchronously (blocking).

    Args:
        host: Server host address
        port: Server port

    Example:
        >>> run_metrics_server(port=8000)
    """
    async def _run() -> None:
        server = MetricsServer(host=host, port=port)
        await server.start()
        logger.info("Press Ctrl+C to stop")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await server.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Shutting down metrics server")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start Prometheus metrics server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_metrics_server(host=args.host, port=args.port)
