"""统一 API 成功响应包络与 OpenAPI 契约。"""

import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

API_PREFIX = "/api/v1"
JSON_MEDIA_TYPE = "application/json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
ENTITY_HEADER_NAMES = {
    b"content-length",
    b"content-type",
    b"content-encoding",
    b"content-md5",
    b"etag",
}


def _is_api_path(path: str) -> bool:
    """判断请求是否属于统一契约的版本化 API。

    Args:
        path: ASGI 请求路径。

    Returns:
        bool: 属于 `/api/v1` 时返回真。
    """
    return path == API_PREFIX or path.startswith(f"{API_PREFIX}/")


def _is_json_response(response: Response) -> bool:
    """判断响应是否为需要包裹的普通 JSON。

    Args:
        response: 下游 FastAPI 响应。

    Returns:
        bool: 2xx、非 204 且媒体类型为 application/json 时返回真。
    """
    content_type = response.headers.get("content-type", "")
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return (
        200 <= response.status_code < 300
        and response.status_code != 204
        and "content-disposition" not in response.headers
        and media_type == JSON_MEDIA_TYPE
    )


def _is_success_envelope(data: Any) -> bool:
    """判断响应是否已经是平台成功包络。

    Args:
        data: JSON 解码后的响应体。

    Returns:
        bool: 同时包含 code=200 和 data 时返回真。
    """
    return (
        isinstance(data, dict)
        and data.get("code") == 200
        and "data" in data
    )


def _preserve_non_entity_headers(
    source: Response,
    target: Response,
) -> None:
    """保留 CORS、Cookie 和业务头，同时重新计算实体相关响应头。

    Args:
        source: 原始响应。
        target: 新 JSON 响应。

    Returns:
        None: 直接修改目标响应原始头列表。
    """
    preserved = [
        (name, value)
        for name, value in source.raw_headers
        if name.lower() not in ENTITY_HEADER_NAMES
    ]
    generated = [
        (name, value)
        for name, value in target.raw_headers
        if name.lower() in {b"content-length", b"content-type"}
    ]
    target.raw_headers = [*preserved, *generated]


class ApiEnvelopeMiddleware(BaseHTTPMiddleware):
    """把版本化 API 的成功 JSON 统一转换为 code/data 包络。"""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """执行下游请求并按媒体类型选择性包裹响应。

        Args:
            request: 当前 HTTP 请求。
            call_next: 下游 ASGI 请求处理器。

        Returns:
            Response: 包裹后的 JSON 或保持原样的非 JSON/错误响应。
        """
        response = await call_next(request)
        if not _is_api_path(request.url.path) or not _is_json_response(response):
            return response
        body_parts = [chunk async for chunk in response.body_iterator]
        body = b"".join(
            part.encode("utf-8") if isinstance(part, str) else part
            for part in body_parts
        )
        data = None if not body else json.loads(body)
        content = data if _is_success_envelope(data) else {
            "code": 200,
            "data": data,
        }
        wrapped = JSONResponse(
            status_code=response.status_code,
            content=content,
            background=response.background,
        )
        _preserve_non_entity_headers(response, wrapped)
        return wrapped


def _success_schema(data_schema: dict[str, Any]) -> dict[str, Any]:
    """构造 OpenAPI 成功包络 Schema。

    Args:
        data_schema: 原业务响应 Schema。

    Returns:
        dict[str, Any]: code/data 对象 Schema。
    """
    return {
        "type": "object",
        "required": ["code", "data"],
        "properties": {
            "code": {
                "type": "integer",
                "enum": [200],
                "description": "平台成功业务码",
            },
            "data": data_schema,
        },
    }


def _error_schema() -> dict[str, Any]:
    """构造 OpenAPI 安全错误包络 Schema。

    Returns:
        dict[str, Any]: code/msg 对象 Schema。
    """
    return {
        "type": "object",
        "required": ["code", "msg"],
        "properties": {
            "code": {"type": "integer", "description": "HTTP/业务错误码"},
            "msg": {"type": "string", "description": "可安全展示的中文错误"},
        },
    }


def wrap_openapi_envelopes(schema: dict[str, Any]) -> dict[str, Any]:
    """就地更新 OpenAPI 中版本化 API 的 JSON 响应契约。

    Args:
        schema: FastAPI 生成的完整 OpenAPI 文档。

    Returns:
        dict[str, Any]: 已同步成功和错误包络的文档。
    """
    for path, path_item in schema.get("paths", {}).items():
        if not _is_api_path(path) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            if operation.get("x-api-envelope") is False:
                continue
            responses = operation.get("responses", {})
            for status_code, response in responses.items():
                if not isinstance(response, dict):
                    continue
                content = response.get("content", {})
                json_content = content.get(JSON_MEDIA_TYPE)
                if not isinstance(json_content, dict):
                    continue
                response_schema = json_content.get("schema")
                if not isinstance(response_schema, dict):
                    continue
                if str(status_code).startswith("2") and str(status_code) != "204":
                    properties = response_schema.get("properties", {})
                    already_wrapped = (
                        isinstance(properties, dict)
                        and "code" in properties
                        and "data" in properties
                    )
                    if not already_wrapped:
                        json_content["schema"] = _success_schema(response_schema)
                elif str(status_code).startswith(("4", "5")):
                    json_content["schema"] = _error_schema()
    return schema


def configure_openapi_envelopes(app: FastAPI) -> None:
    """为 FastAPI 应用安装与运行时一致的 OpenAPI 包络转换。

    Args:
        app: FastAPI 应用。

    Returns:
        None: 替换应用的 OpenAPI 生成函数。
    """
    original_openapi: Callable[[], dict[str, Any]] = app.openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        app.openapi_schema = wrap_openapi_envelopes(original_openapi())
        return app.openapi_schema

    app.openapi = custom_openapi
