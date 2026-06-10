import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from loguru import logger as loguru_logger
import json
from contextlib import asynccontextmanager
from functools import wraps
from typing import Optional, Dict, Any

from app.config import settings, Environment

_BOUND_LOG_KEYS = frozenset({"service", "environment"})


def _format_extra_fields(extra: dict) -> str:
    items = {k: v for k, v in extra.items() if k not in _BOUND_LOG_KEYS}
    if not items:
        return ""
    return " | " + ", ".join(f"{k}={v!r}" for k, v in items.items())


class DevConsoleLogger:
    """Human-readable console output for local development."""

    def sink(self, message) -> None:
        record = message.record
        time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = (
            f"{time_str} | {record['level'].name:8} | "
            f"{record['name']}:{record['function']}:{record['line']} | "
            f"{record['message']}"
        )
        extra = record.get("extra")
        if extra:
            line += _format_extra_fields(extra)

        print(line, file=sys.stderr, flush=True)

        exc = record.get("exception")
        if exc and exc.traceback:
            print(exc.traceback, file=sys.stderr, flush=True)


class ConsoleLogger:
    def __init__(
            self,
            service_name: str,
            environment: str = "",
            include_extra: bool = True
    ) -> None:
        self.service_name = service_name
        self.environment = environment
        self.include_extra = include_extra

    def sink(self, message) -> None:
        record = message.record
        doc = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "environment": self.environment,
            "level": record["level"].name,
            "level_value": record["level"].no,
            "logger": record["name"],
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            "file": record["file"].path,
            "thread": {
                "name": record["thread"].name,
                "id": record["thread"].id
            },
            "process": {
                "name": record["process"].name,
                "id": record["process"].id
            },
            "time": record["time"].isoformat()
        }

        exc = record.get("exception")
        if exc and (exc.type or exc.value):
            doc["exception"] = {
                "type": exc.type.__name__ if exc.type else None,
                "value": str(exc.value) if exc.value else None,
                "traceback": exc.traceback or None
            }

        if self.include_extra:
            extra = record.get("extra")
            if extra:
                doc["extra"] = extra

        print(json.dumps(doc, ensure_ascii=False), flush=True)


@asynccontextmanager
async def async_timer(
        process_name: str,
        logger_instance=None,
        log_start: bool = False,
        extra_data: Optional[Dict[str, Any]] = None
):
    _logger = logger_instance or logger
    _extra = extra_data or {}

    start_time = time.perf_counter()

    if log_start:
        _logger.bind(**_extra).info("Starting: {}", process_name)

    try:
        yield
    except Exception as e:
        end_time = time.perf_counter()
        execution_time = end_time - start_time

        _logger.bind(
            execution_time=execution_time,
            process_name=process_name,
            error_type=type(e).__name__,
            error=str(e),
            **_extra,
        ).opt(exception=e).error(
            "{} failed after {:.3f} sec: {}",
            process_name,
            execution_time,
            str(e),
        )
        raise
    else:
        end_time = time.perf_counter()
        execution_time = end_time - start_time

        _logger.bind(
            execution_time=execution_time,
            process_name=process_name,
            **_extra,
        ).info(
            "{} completed in {:.3f} sec",
            process_name,
            execution_time,
        )


class AsyncTimer:
    def __init__(
            self,
            process_name: str,
            logger_instance=None,
            log_start: bool = False,
            extra_data: Optional[Dict[str, Any]] = None
    ):
        self.process_name = process_name
        self.logger = logger_instance or logger
        self.log_start = log_start
        self.extra_data = extra_data or {}
        self.start_time = None

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        if self.log_start:
            self.logger.bind(**self.extra_data).info("Starting: {}", self.process_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        execution_time = end_time - self.start_time

        if exc_type:
            self.logger.bind(
                execution_time=execution_time,
                process_name=self.process_name,
                error_type=exc_type.__name__,
                error=str(exc_val),
                **self.extra_data,
            ).opt(exception=exc_val).error(
                "{} failed after {:.3f} sec: {}",
                self.process_name,
                execution_time,
                str(exc_val),
            )
        else:
            self.logger.bind(
                execution_time=execution_time,
                process_name=self.process_name,
                **self.extra_data,
            ).info(
                "{} completed in {:.3f} sec",
                self.process_name,
                execution_time,
            )


def log_async_execution_time(
        process_name: Optional[str] = None,
        logger_instance=None,
        extra_data: Optional[Dict[str, Any]] = None
):
    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Function {func.__name__} must be async")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            _process_name = process_name or f"{func.__module__}.{func.__name__}"
            async with async_timer(_process_name, logger_instance, extra_data=extra_data):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def setup_logging(
        service_name: str,
        environment: str,
        level: str = "INFO",
        include_extra: bool = True,
        debug: bool = False,
):
    loguru_logger.remove()
    if debug:
        sink = DevConsoleLogger().sink
    else:
        sink = ConsoleLogger(
            service_name=service_name,
            environment=environment,
            include_extra=include_extra,
        ).sink

    loguru_logger.add(
        sink,
        format="{message}",
        level=level,
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )
    return loguru_logger.bind(service=service_name, environment=environment)


class InterceptHandler(logging.Handler):
    """Route stdlib logging (e.g. aiogram) into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def intercept_stdlib_logging(level: int | None = None) -> None:
    if level is None:
        level = logging.DEBUG if settings.DEBUG else logging.INFO
    logging.basicConfig(handlers=[InterceptHandler()], level=level, force=True)
    for name in ("aiogram", "aiohttp"):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = [InterceptHandler()]
        lib_logger.propagate = False


logger = setup_logging(
    service_name=settings.APP_NAME,
    environment="dev" if settings.ENVIRONMENT == Environment.DEVELOPMENT else "prod",
    level="DEBUG" if settings.DEBUG else "INFO",
    include_extra=True,
    debug=settings.DEBUG,
)