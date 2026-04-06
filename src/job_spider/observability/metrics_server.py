"""Prometheus metrics HTTP server.

Provides a simple HTTP server for exposing Prometheus metrics.
Uses Python's standard library asyncio for minimal dependencies.
"""

import asyncio
import json
import logging

from job_spider.observability.metrics import metrics

logger = logging.getLogger(__name__)


class MetricsServer:
    """HTTP server for Prometheus metrics.

    Uses Python's standard library asyncio for minimal dependencies.

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
        self._server: asyncio.Server | None = None
        self._running = False

    async def start(self) -> None:
        """Start the metrics server."""
        self._server = await asyncio.start_server(
            self._handle_request,
            self.host,
            self.port,
        )
        self._running = True
        logger.info(f"Metrics server started on http://{self.host}:{self.port}")
        logger.info(f"Metrics available at {self.metrics_path}")

    async def stop(self) -> None:
        """Stop the metrics server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._running = False
            logger.info("Metrics server stopped")

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP request.

        Args:
            reader: Stream reader
            writer: Stream writer
        """
        try:
            # Read HTTP request
            request_line = await reader.readline()
            if not request_line:
                return

            try:
                method, path, _ = request_line.decode("utf-8").strip().split(" ", 2)
            except ValueError:
                await self._send_response(writer, 400, "Bad Request")
                return

            # Read headers (discard)
            while True:
                line = await reader.readline()
                if line == b"\r\n" or not line:
                    break

            # Route request
            if path == self.metrics_path:
                await self._handle_metrics(writer)
            elif path == "/health":
                await self._handle_health(writer)
            else:
                await self._send_response(writer, 404, "Not Found")

        except Exception as e:
            logger.debug(f"Error handling request: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_metrics(self, writer: asyncio.StreamWriter) -> None:
        """Handle /metrics request.

        Args:
            writer: Stream writer
        """
        metrics_output = metrics.export_prometheus()
        await self._send_response(
            writer,
            200,
            metrics_output,
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )

    async def _handle_health(self, writer: asyncio.StreamWriter) -> None:
        """Handle /health request.

        Args:
            writer: Stream writer
        """
        await self._send_response(
            writer,
            200,
            json.dumps({"status": "healthy"}),
            content_type="application/json",
        )

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        """Send HTTP response.

        Args:
            writer: Stream writer
            status: HTTP status code
            body: Response body
            content_type: Content-Type header
        """
        status_text = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
        }.get(status, "Unknown")

        response = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()


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
