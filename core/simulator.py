"""算法测试模拟器

提供固定 API（caput/caget）的数学基准函数，用于测试优化算法性能。
已知极值，可加噪声，三种输出模式。
"""
from __future__ import annotations
import time
import numpy as np


# ============ 内置基准函数 ============

def _griewank_fn(x):
    n = len(x)
    offsets = [100.0 * ((i * 137 + 53) % 13 - 6) for i in range(n)]
    s = sum((xi - oi) ** 2 for xi, oi in zip(x, offsets)) / 4000.0
    p = np.prod([np.cos((xi - oi) / np.sqrt(i + 1)) for i, (xi, oi) in enumerate(zip(x, offsets))])
    return float(1.0 + s - p)


BENCHMARK_FUNCTIONS = {
    "griewank": {
        "fn": _griewank_fn,
        "optimum_x": [],
        "optimum_f": 0.0,
        "range": [-600.0, 600.0],
    },
}


# ============ 模拟器 ============

class TestFunctionSimulator:
    """算法测试模拟器 — 固定 API + 已知极值 + 可替换内部函数

    Variables  →  _x[pv] = value
    Objectives →  f(_x.values()) + noise
    """

    def __init__(self, config: dict = None):
        sim_cfg = (config or {}).get("simulation", {})

        self._func_name = sim_cfg.get("function", "griewank")
        self._mode = sim_cfg.get("mode", "scalar")
        self._noise_cfg = sim_cfg.get("noise", {})
        self._image_cfg = sim_cfg.get("image", {})

        # 变量 PV → 值的存储
        self._x: dict[str, float] = {}
        # 变量顺序（来自 config.variables）
        self._var_names: list[str] = []
        if config and "variables" in config:
            for v in config["variables"]:
                self._var_names.append(v["pv"])

        # 初始值：simulation.initial_values 覆盖默认 0.0
        init_vals = sim_cfg.get("initial_values", {})
        for pv_name, init_val in init_vals.items():
            self._x[pv_name] = float(init_val)
        for pv_name in self._var_names:
            if pv_name not in self._x:
                self._x[pv_name] = 0.0

        # 目标 PV 数量（vector 模式自动推算）
        self._n_outputs = 1
        self._obj_pvs_order: list[str] = []   # 目标 PV 的名称顺序
        self._obj_pv_to_idx: dict[str, int] = {}
        if self._mode == "vector" and config:
            objectives = config.get("objectives", {})
            groups = objectives.get("groups", [])
            pv_count = 0
            for g in groups:
                for item in g.get("pvs", []):
                    pv_name = item["pv"] if isinstance(item, dict) else item
                    self._obj_pvs_order.append(pv_name)
                    self._obj_pv_to_idx[pv_name] = pv_count
                    pv_count += 1
            self._n_outputs = max(pv_count, len(self._var_names) or 1)

        # 基准函数
        self._bf = BENCHMARK_FUNCTIONS[self._func_name]

        # 向量模式：预计算灵敏度矩阵（避免每次 caget 都重新生成）
        self._sensitivities_cache = None
        self._baselines_cache = None

        # 统一随机种子（仿真可复现）
        seed = sim_cfg.get("seed", 42)
        self._rng = np.random.RandomState(seed)
        self._seed_sensitivities()

    # ---- 属性 ----

    @property
    def optimum_x(self) -> list[float]:
        """已知极值位置"""
        opt = self._bf["optimum_x"]
        n = len(self._var_names) or 1
        if opt and len(opt) == n:
            return list(opt)
        if self._func_name == "griewank":
            return [100.0 * ((i * 137 + 53) % 13 - 6) for i in range(n)]
        if opt and len(opt) == 1:
            return opt * n
        return [0.0] * n

    @property
    def optimum_f(self) -> float:
        """已知极值值"""
        return self._bf["optimum_f"]

    @property
    def n_vars(self) -> int:
        return len(self._var_names) or 1

    # ---- API ----

    def caput(self, pv: str, value, wait: bool = False,
              timeout: float = 1.0) -> bool:
        self._x[pv] = float(value)
        return True

    def caget(self, pv: str, timeout: float = 1.0):
        # 变量 PV：直接返回存储值
        if pv in self._var_names:
            return self._add_noise(self._x.get(pv, 0.0))

        var_names = self._var_names or list(self._x.keys())
        if not var_names:
            return 0.0

        if self._mode == "vector":
            # 返回该 PV 的独立输出值
            return self._caget_vector_pv(pv)

        x_vals = [self._x.get(v, 0.0) for v in var_names]

        if self._mode == "scalar":
            result = self._bf["fn"](x_vals)
            return self._add_noise(result)

        elif self._mode == "image":
            return self._compute_image_flat()

        return self._add_noise(self._bf["fn"](x_vals))

    def _caget_vector_pv(self, pv: str) -> float:
        """向量模式：返回指定目标 PV 的独立输出值"""
        var_names = self._var_names or list(self._x.keys())
        x_vals = [self._x.get(v, 0.0) for v in var_names]
        idx = self._obj_pv_to_idx.get(pv)
        if idx is None:
            print(f"  警告: 未注册的目标 PV: {pv}")
            return self._add_noise(0.0)
        if idx < len(self._baselines_cache):
            output = float(self._baselines_cache[idx] +
                           self._sensitivities_cache[idx].dot(x_vals))
            return self._add_noise(output)
        return self._add_noise(0.0)

    def caget_many(self, pvs: list[str], timeout: float = 1.0) -> list:
        if self._mode == "vector":
            # 按请求的 PV 顺序返回（以匹配 _all_obj_pvs 的去重顺序）
            all_vals = self._compute_vector()
            if self._obj_pv_to_idx:
                return [all_vals[self._obj_pv_to_idx.get(pv, 0)] for pv in pvs]
            return all_vals
        elif self._mode == "image":
            return self._compute_image_flat()
        return [self.caget(pv, timeout) for pv in pvs]

    def caput_many(self, pvs: list[str], values: list,
                   wait: bool = False, timeout: float = 1.0) -> bool:
        for pv, val in zip(pvs, values):
            self.caput(pv, val, wait, timeout)
        if wait:
            time.sleep(0.1)
        return True

    # ---- 内部计算 ----

    def _add_noise(self, value: float) -> float:
        ntype = self._noise_cfg.get("type", "")
        if not ntype:
            return value
        sigma = self._noise_cfg.get("sigma", 0.0)
        if sigma <= 0:
            return value
        if ntype == "gaussian":
            return value + self._rng.normal(0, sigma)
        return value

    def _seed_sensitivities(self):
        """预计算向量模式的灵敏度和基线（确保每次 caget 返回相同值）"""
        if self._mode != "vector":
            return
        n_vars = len(self._var_names) or 1
        n_out = self._n_outputs
        self._sensitivities_cache = np.zeros((n_out, n_vars))
        for i in range(n_out):
            for j in range(n_vars):
                dist = abs(i - j * (max(n_vars, n_out) / max(n_out, 1)))
                self._sensitivities_cache[i, j] = \
                    (0.5 + 0.5 * self._rng.random()) / (dist + 1.0)
        self._baselines_cache = self._rng.uniform(-0.5, 0.5, n_out)

    def _compute_vector(self) -> list[float]:
        """向量模式：模拟 N 个独立输出"""
        var_names = self._var_names or list(self._x.keys())
        x_vals = [self._x.get(v, 0.0) for v in var_names]
        outputs = self._baselines_cache + self._sensitivities_cache.dot(x_vals)
        return [self._add_noise(float(v)) for v in outputs]

    def _compute_image(self, x_vals: list[float]):
        """图像模式：返回 2D 高斯图像（numpy 数组）"""
        cfg = self._image_cfg
        shape = cfg.get("shape", [256, 256])
        height, width = shape
        center_vars = cfg.get("center_vars", [0, 1])
        size_vars = cfg.get("size_vars", [2, 3])
        bg = cfg.get("background", 10)
        amplitude = cfg.get("amplitude", 5000)

        # 光斑中心
        cx_idx = center_vars[0] if len(center_vars) > 0 else 0
        cy_idx = center_vars[1] if len(center_vars) > 1 else 1
        sx_idx = size_vars[0] if len(size_vars) > 0 else 2
        sy_idx = size_vars[1] if len(size_vars) > 1 else 3

        cx = width / 2 + (x_vals[cx_idx] if cx_idx < len(x_vals) else 0) * width * 0.4
        cy = height / 2 + (x_vals[cy_idx] if cy_idx < len(x_vals) else 0) * height * 0.4
        sigma_x = max(5, 30 + (x_vals[sx_idx] if sx_idx < len(x_vals) else 0) * 20)
        sigma_y = max(5, 30 + (x_vals[sy_idx] if sy_idx < len(x_vals) else 0) * 20)

        gy, gx = np.ogrid[:height, :width]
        img = amplitude * np.exp(
            -0.5 * ((gx - cx) ** 2 / sigma_x ** 2 + (gy - cy) ** 2 / sigma_y ** 2)
        )
        img += self._rng.normal(bg, bg * 0.3, (height, width))
        img = np.maximum(img, 0)
        return img

    def _compute_image_flat(self) -> list:
        """图像模式：返回 flattened 1D Fortran 顺序数组"""
        var_names = self._var_names or list(self._x.keys())
        x_vals = [self._x.get(v, 0.0) for v in var_names]
        img = self._compute_image(x_vals)
        return img.flatten(order="F").tolist()


# ============ 向后兼容 ============
SimpleEPICSSimulator = TestFunctionSimulator


# ============ 全局实例 + 导出函数 ============
_simulator = TestFunctionSimulator()


def set_simulator_config(config: dict) -> None:
    """根据配置重建模拟器实例

    Args:
        config: 完整配置字典（含 simulation 字段）
    """
    global _simulator
    _simulator = TestFunctionSimulator(config)


def caget(pv, timeout=1.0):
    return _simulator.caget(pv, timeout)


def caput(pv, value, wait=False, timeout=1.0):
    return _simulator.caput(pv, value, wait, timeout)


def caget_many(pvs, timeout=1.0):
    return _simulator.caget_many(pvs, timeout)


def caput_many(pvs, values, wait=False, timeout=1.0):
    return _simulator.caput_many(pvs, values, wait, timeout)
