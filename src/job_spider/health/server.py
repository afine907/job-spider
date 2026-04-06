"""
Health check server for K8s/Docker health probes.

Provides lightweight HTTP endpoints for:
- /health - Liveness probe (process alive)
- /ready - Readiness probe (database connection, config loaded)
"""

import asyncio
import json
from pathlib import Path
from typing import Callable

from config.logging import get_logger
from config.settings import get_settings

logger = get_logger("health")


class HealthServer:
    """
    Lightweight async HTTP health check server.

    Uses Python's standard library asyncio for minimal dependencies.
    Designed for K8s/Docker health probes without blocking the main process.

    Example:
        >>> server = HealthServer(port=8080)
        >>> await server.start()
        >>> # Server runs in background
        >>> await server.stop()
    """

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        custom_checks: dict[str, Callable] | None = None,
    ):
        """
        Initialize health server.

        Args:
            port: HTTP server port (default: 8080)
            host: Bind address (default: 0.0.0.0 for all interfaces)
            custom_checks: Optional dict of custom health check functions
        """
        self.port = port
        self.host = host
        self.custom_checks = custom_checks or {}
        self._server = None
        self._running = False

    async def start(self) -> None:
        """Start the health check server in background."""
        self._server = await asyncio.start_server(
            self._handle_request,
            self.host,
            self.port,
        )
        self._running = True
        logger.info(
            "Health server started",
            host=self.host,
            port=self.port,
        )

    async def stop(self) -> None:
        """Stop the health check server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._running = False
            logger.info("Health server stopped")

    async def serve_forever(self) -> None:
        """Run the server until stopped (blocking)."""
        if not self._server:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP request."""
        try:
            # Read HTTP request with timeout
            try:
                request_data = await asyncio.wait_for(
                    reader.read(4096),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                await self._send_response(writer, 408, {"error": "Request timeout"})
                return

            request = request_data.decode("utf-8", errors="ignore")

            # Parse request line
            lines = request.split("\r\n")
            if not lines:
                await self._send_response(writer, 400, {"error": "Bad request"})
                return

            request_line = lines[0].split()
            if len(request_line) < 2:
                await self._send_response(writer, 400, {"error": "Bad request"})
                return

            method = request_line[0]
            path = request_line[1]

            # Route request
            if method == "GET":
                if path == "/health":
                    await self._handle_health(writer)
                elif path == "/ready":
                    await self._handle_ready(writer)
                else:
                    await self._send_response(writer, 404, {"error": "Not found"})
            else:
                await self._send_response(writer, 405, {"error": "Method not allowed"})

        except Exception as e:
            logger.error("Health check request failed", error=str(e))
            try:
                await self._send_response(writer, 500, {"error": "Internal error"})
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_health(self, writer: asyncio.StreamWriter) -> None:
        """
        Handle /health endpoint - liveness probe.

        Returns 200 if process is alive and can handle requests.
        """
        response = {"status": "healthy"}
        await self._send_response(writer, 200, response)
        logger.debug("Health check passed")

    async def _handle_ready(self, writer: asyncio.StreamWriter) -> None:
        """
        Handle /ready endpoint - readiness probe.

        Returns 200 if all dependencies are ready:
        - Database connection works
        - Configuration loaded
        - Custom checks pass
        """
        checks: dict[str, bool] = {}
        all_ready = True

        # Check database
        db_ready = await self._check_database()
        checks["database"] = db_ready
        if not db_ready:
            all_ready = False

        # Check configuration
        config_ready = self._check_config()
        checks["config"] = config_ready
        if not config_ready:
            all_ready = False

        # Run custom checks
        for name, check_fn in self.custom_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()
                checks[name] = bool(result)
                if not result:
                    all_ready = False
            except Exception as e:
                logger.warning("Custom check failed", name=name, error=str(e))
                checks[name] = False
                all_ready = False

        status_code = 200 if all_ready else 503
        response = {
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
        }
        await self._send_response(writer, status_code, response)
        logger.debug("Readiness check", all_ready=all_ready, checks=checks)

    async def _check_database(self) -> bool:
        """Check database connection health."""
        try:
            settings = get_settings()
            db_path = Path(settings.database.sqlite_path)

            # For SQLite, check if file exists and is accessible
            if not db_path.exists():
                # Database file doesn't exist yet - considered ready
                # (might not have been initialized)
                return True

            # Try to read file to verify accessibility
            import aiosqlite

            async with aiosqlite.connect(str(db_path)) as db:
                await db.execute("SELECT 1")
                await db.fetchone()
            return True

        except Exception as e:
            logger.warning("Database health check failed", error=str(e))
            return False

    def _check_config(self) -> bool:
        """Check configuration loaded correctly."""
        try:
            settings = get_settings()
            # Verify essential config values exist
            _ = settings.project_name
            _ = settings.version
            return True
        except Exception as e:
            logger.warning("Config health check failed", error=str(e))
            return False

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        body: dict,
    ) -> None:
        """Send HTTP response."""
        status_messages = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            408: "Request Timeout",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }

        status_message = status_messages.get(status_code, "Unknown")
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

        response = (
            f"HTTP/1.1 {status_code} {status_message}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8")

        writer.write(response + body_bytes)
        await writer.drain()


async def run_health_server(
    port: int = 8080,
    host: str = "0.0.0.0",
    daemon: bool = False,
) -> None:
    """
    Run health check server.

    Args:
        port: Server port (default: 8080)
        host: Bind address (default: 0.0.0.0)
        daemon: Run as background task (not blocking)

    Example:
        >>> # Blocking mode
        >>> await run_health_server(port=8080)

        >>> # Background mode
        >>> task = asyncio.create_task(run_health_server(port=8080, daemon=True))
        >>> # Do other work...
        >>> task.cancel()
    """
    server = HealthServer(port=port, host=host)
    await server.start()

    if not daemon:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            await server.stop()
