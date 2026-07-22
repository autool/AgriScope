"""版本化 API 成功包络与 OpenAPI 契约测试。"""

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.api_envelope import (
    ApiEnvelopeMiddleware,
    configure_openapi_envelopes,
)


class ItemResponse(BaseModel):
    """测试业务对象。"""

    item_id: int
    name: str


def build_app() -> FastAPI:
    """构造不依赖数据库的最小包络测试应用。"""
    app = FastAPI()
    app.add_middleware(ApiEnvelopeMiddleware)

    @app.get("/api/v1/items/{item_id}", response_model=ItemResponse)
    async def get_item(item_id: int) -> ItemResponse:
        return ItemResponse(item_id=item_id, name="真实业务对象")

    @app.post("/api/v1/items", status_code=201)
    async def create_item() -> JSONResponse:
        return JSONResponse(
            status_code=201,
            content={"item_id": 2},
            headers={"X-Audit-Code": "AUDIT-001"},
        )

    @app.get("/api/v1/already-wrapped")
    async def already_wrapped() -> dict:
        return {"code": 200, "data": {"value": 1}}

    @app.get("/api/v1/rejected")
    async def rejected() -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "msg": "请求不符合业务规则"},
        )

    @app.get("/api/v1/raster")
    async def raster() -> Response:
        return Response(
            content=b"TIFF-DATA",
            media_type="image/tiff",
            headers={"ETag": '"raster-sha256"'},
        )

    @app.get(
        "/api/v1/report",
        response_class=Response,
        responses={200: {"content": {"application/json": {}}}},
        openapi_extra={"x-api-envelope": False},
    )
    async def report() -> Response:
        return Response(
            content=b'{"report":"physical-artifact"}',
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="report.json"'},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    configure_openapi_envelopes(app)
    return app


@pytest.mark.asyncio
async def test_success_json_is_wrapped_and_http_status_is_preserved() -> None:
    """验证 200/201 JSON 使用 code/data，且业务状态码和审计头不丢失。"""
    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        get_response = await client.get("/api/v1/items/7")
        create_response = await client.post("/api/v1/items")

    assert get_response.status_code == 200
    assert get_response.json() == {
        "code": 200,
        "data": {"item_id": 7, "name": "真实业务对象"},
    }
    assert create_response.status_code == 201
    assert create_response.json() == {"code": 200, "data": {"item_id": 2}}
    assert create_response.headers["x-audit-code"] == "AUDIT-001"
    assert int(create_response.headers["content-length"]) == len(
        create_response.content
    )


@pytest.mark.asyncio
async def test_non_success_or_non_json_responses_are_unchanged() -> None:
    """验证不会双重包裹，也不会破坏错误、文件及非版本化健康检查。"""
    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        wrapped = await client.get("/api/v1/already-wrapped")
        rejected = await client.get("/api/v1/rejected")
        raster = await client.get("/api/v1/raster")
        report = await client.get("/api/v1/report")
        health = await client.get("/health")

    assert wrapped.json() == {"code": 200, "data": {"value": 1}}
    assert rejected.status_code == 400
    assert rejected.json() == {"code": 400, "msg": "请求不符合业务规则"}
    assert raster.content == b"TIFF-DATA"
    assert raster.headers["content-type"] == "image/tiff"
    assert raster.headers["etag"] == '"raster-sha256"'
    assert report.json() == {"report": "physical-artifact"}
    assert report.headers["content-disposition"].startswith("attachment")
    assert health.json() == {"status": "ok"}


def test_openapi_documents_success_and_error_envelopes() -> None:
    """验证 OpenAPI 与运行时成功/错误响应结构一致。"""
    schema = build_app().openapi()
    operation = schema["paths"]["/api/v1/items/{item_id}"]["get"]
    success = operation["responses"]["200"]["content"]["application/json"]["schema"]
    validation_error = operation["responses"]["422"]["content"][
        "application/json"
    ]["schema"]

    assert success["required"] == ["code", "data"]
    assert success["properties"]["code"]["enum"] == [200]
    assert success["properties"]["data"]["$ref"].endswith("/ItemResponse")
    assert validation_error["required"] == ["code", "msg"]
    assert set(validation_error["properties"]) == {"code", "msg"}
    report_schema = schema["paths"]["/api/v1/report"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]
    assert "schema" not in report_schema
    assert schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {
        "additionalProperties": {"type": "string"},
        "type": "object",
        "title": "Response Health Health Get",
    }
