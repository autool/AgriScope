"""FastAPI 应用入口。"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.api.v1.endpoints import (
    boundary,
    change_detection,
    delivery,
    disaster,
    field_verification,
    health,
    imagery,
    imagery_fusion,
    imagery_history,
    imagery_mosaic,
    imagery_registration,
    monitoring_network,
    plot,
    production,
    project_user,
    review,
    rule_config,
    service_sharing,
    statistics,
    supervision,
    thematic_map,
    uav,
    workbench,
)
from app.core.api_envelope import ApiEnvelopeMiddleware, configure_openapi_envelopes
from app.core.config import settings
from app.core.database import async_engine
from app.core.exceptions import AppException

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """启动时重试数据库连接，关闭时释放连接池。

    最多重试 15 次，每次间隔 2 秒，避免 PostGIS 尚未就绪导致应用退出。

    Args:
        _: 当前 FastAPI 应用实例。

    Returns:
        AsyncGenerator[None, None]: 应用生命周期异步生成器。
    """
    max_attempts = 15
    for attempt in range(1, max_attempts + 1):
        try:
            async with async_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            logger.info("数据库连接成功，尝试次数=%s", attempt)
            break
        except (ConnectionError, DBAPIError, OSError):
            logger.warning("数据库暂不可用，尝试次数=%s/%s", attempt, max_attempts)
            if attempt == max_attempts:
                logger.exception("数据库连接重试耗尽")
                raise RuntimeError("数据库连接失败，应用无法启动") from None
            await asyncio.sleep(2)

    try:
        yield
    finally:
        await async_engine.dispose()
        logger.info("数据库连接池已释放")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiEnvelopeMiddleware)


@app.exception_handler(AppException)
async def handle_app_exception(
    _: Request,
    exc: AppException,
) -> JSONResponse:
    """将可预期业务异常转换为统一安全响应。

    Args:
        _: 当前 HTTP 请求。
        exc: 业务异常实例。

    Returns:
        JSONResponse: 统一错误结构。
    """
    return JSONResponse(
        status_code=exc.code,
        content={"code": exc.code, "msg": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """隐藏内部校验细节并返回统一参数错误。

    Args:
        _: 当前 HTTP 请求。
        exc: FastAPI 请求校验异常。

    Returns:
        JSONResponse: 参数错误响应。
    """
    logger.info("请求参数校验失败: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": "请求参数不合法"},
    )


@app.exception_handler(IntegrityError)
@app.exception_handler(DBAPIError)
@app.exception_handler(SQLAlchemyError)
@app.exception_handler(ConnectionError)
async def handle_database_exception(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    """记录数据库异常堆栈，对前端仅返回通用提示。

    Args:
        _: 当前 HTTP 请求。
        exc: 数据库或连接异常。

    Returns:
        JSONResponse: 不含数据库详情的通用错误响应。
    """
    logger.exception("数据库操作异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "系统繁忙"},
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    """兜底处理未预期异常，防止内部堆栈泄露。

    Args:
        _: 当前 HTTP 请求。
        exc: 未预期异常。

    Returns:
        JSONResponse: 通用服务器错误响应。
    """
    logger.exception("未处理的应用异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "系统繁忙"},
    )


app.include_router(health.router)
app.include_router(plot.router)
app.include_router(project_user.router)
app.include_router(workbench.router)
app.include_router(field_verification.router)
app.include_router(review.router)
app.include_router(statistics.router)
app.include_router(disaster.router)
app.include_router(imagery.router)
app.include_router(imagery_fusion.router)
app.include_router(imagery_history.router)
app.include_router(imagery_mosaic.router)
app.include_router(imagery_registration.router)
app.include_router(delivery.router)
app.include_router(boundary.router)
app.include_router(rule_config.router)
app.include_router(service_sharing.router)
app.include_router(production.router)
app.include_router(change_detection.router)
app.include_router(supervision.router)
app.include_router(thematic_map.router)
app.include_router(monitoring_network.router)
app.include_router(uav.router)
configure_openapi_envelopes(app)
