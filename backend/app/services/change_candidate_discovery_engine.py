"""基于双时相公共网格 PNG 的确定性 RGB 差分候选发现引擎。"""

import warnings
from dataclasses import dataclass

import numpy as np
from rasterio.errors import NotGeoreferencedWarning
from rasterio.features import geometry_mask, shapes, sieve
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds


@dataclass(frozen=True)
class DiscoveredChangeGeometry:
    """单个差分连通域的 Polygon、置信度和像元证据。"""

    geometry: dict
    confidence: float
    pixel_count: int


@dataclass(frozen=True)
class ChangeCandidateDiscoveryResult:
    """候选发现结果和算法统计。"""

    candidates: tuple[DiscoveredChangeGeometry, ...]
    changed_pixel_count: int
    valid_pixel_count: int


class ChangeCandidateDiscoveryEngine:
    """执行共同拉伸 RGB 绝对差分、连通域筛选和 Polygon 矢量化。"""

    algorithm_code = "rgb_absolute_difference"
    algorithm_version = "1.0.0"

    @staticmethod
    def _read_rgba(png: bytes) -> np.ndarray:
        """读取服务端生成的 RGBA PNG 为四通道 uint8 数组。

        Args:
            png: PNG 文件字节。

        Returns:
            np.ndarray: 通道优先 RGBA 数组。
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with MemoryFile(png) as memory:
                with memory.open() as dataset:
                    if dataset.count != 4:
                        raise ValueError("双时相预览必须为 RGBA PNG")
                    return dataset.read()

    def discover(
        self,
        baseline_png: bytes,
        target_png: bytes,
        bounds_wgs84: tuple[float, float, float, float],
        difference_threshold: float,
        min_component_pixels: int,
        max_candidates: int,
    ) -> ChangeCandidateDiscoveryResult:
        """发现显著 RGB 差分连通域并转换为 WGS84 Polygon。

        Args:
            baseline_png: 前时相共同网格 PNG。
            target_png: 后时相共同网格 PNG。
            bounds_wgs84: PNG 对应 WGS84 公共范围。
            difference_threshold: 0–1 平均 RGB 绝对差分阈值。
            min_component_pixels: 连通域最小像元数。
            max_candidates: 允许输出的最大候选数量。

        Returns:
            ChangeCandidateDiscoveryResult: 候选 Polygon 和像元统计。
        """
        if not 0.01 <= difference_threshold <= 1:
            raise ValueError("RGB 差分阈值必须为 0.01–1")
        if not 1 <= min_component_pixels <= 100_000:
            raise ValueError("最小连通域像元数必须为 1–100000")
        if not 1 <= max_candidates <= 500:
            raise ValueError("自动候选上限必须为 1–500")
        baseline = self._read_rgba(baseline_png)
        target = self._read_rgba(target_png)
        if baseline.shape != target.shape:
            raise ValueError("前后时相公共网格尺寸不一致")
        valid_mask = (baseline[3] > 0) & (target[3] > 0)
        valid_pixel_count = int(np.count_nonzero(valid_mask))
        if valid_pixel_count == 0:
            raise ValueError("前后时相公共网格没有共同有效像元")
        baseline_rgb = baseline[:3].astype("float32") / 255
        target_rgb = target[:3].astype("float32") / 255
        difference = np.mean(np.abs(target_rgb - baseline_rgb), axis=0)
        binary = ((difference >= difference_threshold) & valid_mask).astype("uint8")
        if min_component_pixels > 1:
            binary = sieve(
                binary,
                size=min_component_pixels,
                connectivity=8,
            ).astype("uint8")
        changed_pixel_count = int(np.count_nonzero(binary))
        if changed_pixel_count == 0:
            return ChangeCandidateDiscoveryResult(
                candidates=(),
                changed_pixel_count=0,
                valid_pixel_count=valid_pixel_count,
            )
        height, width = binary.shape
        transform = from_bounds(*bounds_wgs84, width, height)
        candidates: list[DiscoveredChangeGeometry] = []
        for geometry, value in shapes(
            binary,
            mask=binary.astype(bool),
            connectivity=8,
            transform=transform,
        ):
            if int(value) != 1 or geometry.get("type") != "Polygon":
                continue
            component_mask = geometry_mask(
                [geometry],
                out_shape=(height, width),
                transform=transform,
                invert=True,
            ) & binary.astype(bool)
            pixel_count = int(np.count_nonzero(component_mask))
            if pixel_count < min_component_pixels:
                continue
            confidence = float(np.mean(difference[component_mask]))
            candidates.append(
                DiscoveredChangeGeometry(
                    geometry=geometry,
                    confidence=round(min(max(confidence, 0), 1), 5),
                    pixel_count=pixel_count,
                )
            )
        candidates.sort(key=lambda item: (-item.confidence, -item.pixel_count))
        if len(candidates) > max_candidates:
            raise ValueError(
                f"检测到 {len(candidates)} 个候选，超过上限 {max_candidates}，"
                "请提高差分阈值或最小连通域像元数"
            )
        return ChangeCandidateDiscoveryResult(
            candidates=tuple(candidates),
            changed_pixel_count=changed_pixel_count,
            valid_pixel_count=valid_pixel_count,
        )
