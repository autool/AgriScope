"""Planetary Computer 固定公开 STAC 来源访问客户端。"""

import json
from datetime import date
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from app.core.exceptions import NotFoundException, ValidationException


class PublicImageryClient:
    """仅访问受控 Planetary Computer Landsat STAC 和 SAS 签名端点。"""

    STAC_ROOT = "https://planetarycomputer.microsoft.com/api/stac/v1"
    COLLECTION = "landsat-c2-l2"
    SEARCH_URL = f"{STAC_ROOT}/search"
    SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
    USER_AGENT = "AgriScope-public-landsat-archive/1.0"

    def search(
        self,
        bbox: tuple[float, float, float, float],
        start_date: date,
        end_date: date,
        max_cloud_cover: float,
    ) -> list[dict[str, Any]]:
        """检索固定 Landsat Collection 2 Level-2 候选。

        Args:
            bbox: WGS84 检索范围。
            start_date: 开始日期。
            end_date: 结束日期。
            max_cloud_cover: 最大云量百分比。

        Returns:
            list[dict[str, Any]]: STAC Feature 列表。
        """
        payload = {
            "collections": [self.COLLECTION],
            "bbox": list(bbox),
            "datetime": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "limit": 40,
            "query": {"eo:cloud_cover": {"lte": max_cloud_cover}},
        }
        body = self._request_json(
            self.SEARCH_URL,
            method="POST",
            payload=payload,
        )
        features = body.get("features")
        if not isinstance(features, list):
            raise ValidationException("公开 STAC 检索响应缺少候选列表")
        return [item for item in features if isinstance(item, dict)]

    def get_item(self, item_id: str) -> dict[str, Any]:
        """按服务端固定 collection 重新读取一个 STAC Item。

        Args:
            item_id: Landsat STAC Item ID。

        Returns:
            dict[str, Any]: 服务端重新获取的 STAC Feature。
        """
        item_url = self.item_url(item_id)
        try:
            return self._request_json(item_url, method="GET")
        except NotFoundException:
            raise
        except ValidationException as exc:
            raise ValidationException("公开 Landsat 条目读取失败") from exc

    def sign_asset_url(self, unsigned_href: str) -> str:
        """为 Planetary Computer 返回的公开 Blob URL申请短期 SAS。

        Args:
            unsigned_href: STAC Item 中的原始无签名资产 URL。

        Returns:
            str: 仅用于本次服务端读取的短期签名 URL。
        """
        self._validate_unsigned_asset_url(unsigned_href)
        body = self._request_json(
            f"{self.SIGN_URL}?{urlencode({'href': unsigned_href})}",
            method="GET",
        )
        signed_href = body.get("href")
        if not isinstance(signed_href, str) or not signed_href:
            raise ValidationException("公开影像签名服务未返回可用地址")
        unsigned = urlparse(unsigned_href)
        signed = urlparse(signed_href)
        if (
            signed.scheme != "https"
            or signed.hostname != unsigned.hostname
            or signed.path != unsigned.path
            or not signed.query
        ):
            raise ValidationException("公开影像签名地址未通过来源一致性校验")
        return signed_href

    @classmethod
    def item_url(cls, item_id: str) -> str:
        """生成固定 collection 下的公开 STAC Item URL。

        Args:
            item_id: Landsat STAC Item ID。

        Returns:
            str: 不含令牌的公开 STAC Item URL。
        """
        encoded = quote(item_id, safe="")
        return f"{cls.STAC_ROOT}/collections/{cls.COLLECTION}/items/{encoded}"

    @staticmethod
    def _validate_unsigned_asset_url(href: str) -> None:
        """限制签名目标为 Planetary Computer 使用的 Azure Blob HTTPS URL。

        Args:
            href: STAC 返回的无签名资产地址。

        Returns:
            None: 校验通过后无返回值。
        """
        parsed = urlparse(href)
        hostname = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or not hostname.endswith(".blob.core.windows.net")
            or parsed.query
            or not parsed.path.lower().endswith((".tif", ".tiff"))
        ):
            raise ValidationException("公开影像资产地址不属于受控 Azure COG 来源")

    def _request_json(
        self,
        url: str,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行固定端点 JSON 请求并转换为安全业务异常。

        Args:
            url: 已由本客户端构造的固定端点。
            method: GET 或 POST。
            payload: 可选 JSON 请求体。

        Returns:
            dict[str, Any]: JSON 对象响应。
        """
        data = None
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                body = json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                raise NotFoundException("公开 Landsat 条目不存在") from exc
            raise ValidationException("公开影像服务暂时不可用") from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise ValidationException("公开影像服务连接失败，请稍后重试") from exc
        except JSONDecodeError as exc:
            raise ValidationException("公开影像服务响应不是合法 JSON") from exc
        if not isinstance(body, dict):
            raise ValidationException("公开影像服务响应结构不合法")
        return body
