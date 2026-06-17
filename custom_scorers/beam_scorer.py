"""束流尺寸优化数据变换"""
import numpy as np
from core.transforms.base import Transform
from core.transforms.registry import register_transform


BEAM_MODE_WEIGHTS = {
    "size_focus":      {"size": 0.7, "roundness": 0.3, "position": 0.0},
    "balanced":        {"size": 0.5, "roundness": 0.4, "position": 0.1},
    "roundness_focus": {"size": 0.3, "roundness": 0.6, "position": 0.1},
}


@register_transform("beam_optimizer")
class BeamOptimizerTransform(Transform):
    """束流尺寸优化变换

    输入: 1D 数组（CCD 原始数据，Fortran 顺序）
    输出: float（加权综合评分：尺寸 + 圆度 + 位置保持）

    配置示例:
        "transform": {
            "type": "custom:beam_optimizer",
            "params": {
                "shape": [1392, 1040],
                "order": "F",
                "beam_mode": "balanced",
                "maintain_position": true
            }
        }
    """

    def __init__(self, params: dict = None):
        super().__init__(params)
        self.camera_shape = self.params.get("shape", [1392, 1040])
        self.order = self.params.get("order", "F")
        self.beam_mode = self.params.get("beam_mode", "balanced")
        self.maintain_position = self.params.get("maintain_position", True)
        self._mode_weights = BEAM_MODE_WEIGHTS.get(
            self.beam_mode, BEAM_MODE_WEIGHTS["balanced"]
        )
        self._initial_centroid = None


    def __call__(self, raw_value, *, pv_name="", caget_fn=None):
        img = np.asarray(raw_value, dtype=np.float32)
        shape = self.camera_shape

        if len(img.shape) == 1 and img.size == shape[0] * shape[1]:
            img = img.reshape(shape, order=self.order)
        if img.ndim != 2:
            return float("inf")

        size_x, size_y, centroid_x, centroid_y = self._spot_metrics(img)
        if size_x <= 0 or size_y <= 0:
            return float("inf")

        w = self._mode_weights
        diagonal = np.sqrt(size_x ** 2 + size_y ** 2)
        roundness = (min(size_x, size_y) / max(size_x, size_y)
                     if max(size_x, size_y) > 0 else 0)

        size_score = diagonal
        roundness_penalty = diagonal * (1.0 - roundness)

        position_penalty = 0.0
        if self.maintain_position:
            if self._initial_centroid is None:
                self._initial_centroid = (centroid_x, centroid_y)
            dx = centroid_x - self._initial_centroid[0]
            dy = centroid_y - self._initial_centroid[1]
            distance = np.sqrt(dx ** 2 + dy ** 2)
            img_diag = np.sqrt(shape[0] ** 2 + shape[1] ** 2)
            position_penalty = diagonal * (distance / img_diag) * 100

        return float(
            w["size"] * size_score
            + w["roundness"] * roundness_penalty
            + w["position"] * position_penalty
        )


    @staticmethod
    def _spot_metrics(img):
        """计算束斑尺寸和质心（FWHM 阈值法）"""
        if img.size == 0 or np.max(img) < 1e-9:
            return -1, -1, -1, -1

        from scipy.ndimage import gaussian_filter

        flat = img.flatten()
        bg_pixels = np.sort(flat)[:int(0.2 * img.size)]
        bg_std = float(np.std(bg_pixels))
        sigma = 1.0 if bg_std < 15 else 2.0
        denoised = gaussian_filter(img, sigma=sigma)

        background = float(np.percentile(denoised, max(5, min(20, bg_std * 2))))
        subtracted = np.maximum(denoised - background, 0)
        max_val = float(np.max(subtracted))
        if max_val < bg_std * 3:
            return -1, -1, -1, -1

        beam_mask = subtracted > max_val * 0.5
        if np.sum(beam_mask) < 5:
            return -1, -1, -1, -1

        x_proj = np.sum(beam_mask, axis=0)
        y_proj = np.sum(beam_mask, axis=1)
        x_idx = np.where(x_proj > 0)[0]
        y_idx = np.where(y_proj > 0)[0]
        if len(x_idx) < 2 or len(y_idx) < 2:
            return -1, -1, -1, -1

        size_x = float(x_idx[-1] - x_idx[0])
        size_y = float(y_idx[-1] - y_idx[0])

        y_coords, x_coords = np.where(beam_mask)
        centroid_x = float(np.mean(x_coords))
        centroid_y = float(np.mean(y_coords))

        return size_x, size_y, centroid_x, centroid_y
