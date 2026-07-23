"""基于双时相公共网格 PNG 的可审计多算法变化候选发现引擎。"""

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

    algorithm_code: str
    algorithm_name: str
    algorithm_version: str
    score_formula: str
    candidates: tuple[DiscoveredChangeGeometry, ...]
    changed_pixel_count: int
    valid_pixel_count: int


@dataclass(frozen=True)
class ChangeCandidateDiscoveryAlgorithm:
    """一个可由前端选择且可在成果中复核的变化分数算法。"""

    code: str
    name: str
    version: str
    description: str
    score_formula: str
    default_threshold: float
    threshold_min: float = 0.01
    threshold_max: float = 1.0


class ChangeCandidateDiscoveryEngine:
    """执行 RGB 变化评分、四邻域筛选和 Polygon 矢量化。"""

    algorithms = (
        ChangeCandidateDiscoveryAlgorithm(
            code="rgb_absolute_difference",
            name="RGB 平均绝对差分",
            version="1.2.0",
            description=(
                "计算三个共同拉伸 RGB 通道绝对变化的平均值，适合整体亮度或"
                "综合色彩变化筛查。"
            ),
            score_formula="mean(abs(target_rgb - baseline_rgb))",
            default_threshold=0.18,
        ),
        ChangeCandidateDiscoveryAlgorithm(
            code="rgb_change_vector",
            name="RGB 变化向量幅值",
            version="1.0.0",
            description=(
                "计算三个 RGB 通道变化向量的归一化欧氏幅值，对单一通道的"
                "强变化更敏感。"
            ),
            score_formula="sqrt(mean((target_rgb - baseline_rgb)^2))",
            default_threshold=0.22,
        ),
    )

    @classmethod
    def algorithm_descriptors(
        cls,
    ) -> tuple[ChangeCandidateDiscoveryAlgorithm, ...]:
        """返回服务端实际支持的候选发现算法注册表。

        Returns:
            tuple[ChangeCandidateDiscoveryAlgorithm, ...]: 算法能力清单。
        """
        return cls.algorithms

    @classmethod
    def _resolve_algorithm(
        cls,
        algorithm_code: str,
    ) -> ChangeCandidateDiscoveryAlgorithm:
        """按编码解析算法并拒绝未注册实现。

        Args:
            algorithm_code: 请求选择的算法编码。

        Returns:
            ChangeCandidateDiscoveryAlgorithm: 已注册算法描述。
        """
        for algorithm in cls.algorithms:
            if algorithm.code == algorithm_code:
                return algorithm
        raise ValueError(f"不支持的变化候选算法：{algorithm_code}")

    @classmethod
    def algorithm_descriptor(
        cls,
        algorithm_code: str,
    ) -> ChangeCandidateDiscoveryAlgorithm:
        """返回指定服务端算法描述。

        Args:
            algorithm_code: 已注册算法编码。

        Returns:
            ChangeCandidateDiscoveryAlgorithm: 算法描述和默认阈值。
        """
        return cls._resolve_algorithm(algorithm_code)

    @staticmethod
    def _difference_score(
        baseline_rgb: np.ndarray,
        target_rgb: np.ndarray,
        algorithm_code: str,
    ) -> np.ndarray:
        """按注册算法计算每个有效像元的 0–1 变化分数。

        Args:
            baseline_rgb: 前时相归一化 RGB 数组。
            target_rgb: 后时相归一化 RGB 数组。
            algorithm_code: 已注册算法编码。

        Returns:
            np.ndarray: 二维变化分数数组。
        """
        delta = target_rgb - baseline_rgb
        if algorithm_code == "rgb_absolute_difference":
            return np.mean(np.abs(delta), axis=0)
        if algorithm_code == "rgb_change_vector":
            return np.sqrt(np.mean(np.square(delta), axis=0))
        raise ValueError(f"不支持的变化候选算法：{algorithm_code}")

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
        algorithm_code: str,
        difference_threshold: float,
        min_component_pixels: int,
        max_candidates: int,
    ) -> ChangeCandidateDiscoveryResult:
        """发现显著 RGB 差分连通域并转换为 WGS84 Polygon。

        Args:
            baseline_png: 前时相共同网格 PNG。
            target_png: 后时相共同网格 PNG。
            bounds_wgs84: PNG 对应 WGS84 公共范围。
            algorithm_code: 服务端注册的变化分数算法编码。
            difference_threshold: 0–1 变化分数阈值。
            min_component_pixels: 连通域最小像元数。
            max_candidates: 允许输出的最大候选数量。

        Returns:
            ChangeCandidateDiscoveryResult: 候选 Polygon 和像元统计。
        """
        algorithm = self._resolve_algorithm(algorithm_code)
        if not algorithm.threshold_min <= difference_threshold <= (
            algorithm.threshold_max
        ):
            raise ValueError(
                f"{algorithm.name}阈值必须为 "
                f"{algorithm.threshold_min:g}–{algorithm.threshold_max:g}"
            )
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
        difference = self._difference_score(
            baseline_rgb,
            target_rgb,
            algorithm.code,
        )
        binary = ((difference >= difference_threshold) & valid_mask).astype("uint8")
        if min_component_pixels > 1:
            # 四邻域避免仅在角点接触的像元被合并成自接触环；这类八邻域
            # Polygon 会被 PostGIS 判定为无效，且不应作为正式变化候选。
            binary = sieve(
                binary,
                size=min_component_pixels,
                connectivity=4,
            ).astype("uint8")
        changed_pixel_count = int(np.count_nonzero(binary))
        if changed_pixel_count == 0:
            return ChangeCandidateDiscoveryResult(
                algorithm_code=algorithm.code,
                algorithm_name=algorithm.name,
                algorithm_version=algorithm.version,
                score_formula=algorithm.score_formula,
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
            connectivity=4,
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
            algorithm_code=algorithm.code,
            algorithm_name=algorithm.name,
            algorithm_version=algorithm.version,
            score_formula=algorithm.score_formula,
            candidates=tuple(candidates),
            changed_pixel_count=changed_pixel_count,
            valid_pixel_count=valid_pixel_count,
        )
