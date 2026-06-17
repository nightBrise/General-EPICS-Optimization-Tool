"""硬件控制器：caput + 验证 + 等待稳定 + 回滚"""
import time
from .epics_backend import caget, caput, caget_many


class HardwareController:
    """处理与 EPICS 硬件的所有交互

    职责：
    - 安全设置变量 PV（caput + 读回验证）
    - 等待所有设备达到设定值
    - 失败时回滚到初始值
    """

    def __init__(self, config: dict):
        hardware = config.get('hardware', {})
        self.tolerance = hardware.get('tolerance', 0.0001)
        self.max_wait = hardware.get('max_wait', 10)
        self.poll_interval = hardware.get('poll_interval', 0.2)
        self.min_adjust_interval = hardware.get('min_adjust_interval', 6)
        self.rollback_on_failure = hardware.get('rollback_on_failure', True)
        self.write_retries = hardware.get('write_retries', 3)

        self._initial_pvs: list[str] = []
        self._initial_values: list[float] = []
        self._last_adjust_time: float = 0

    def save_initial(self, pvs: list[str], values: list[float]):
        """保存初始值（用于回滚）

        Args:
            pvs: 变量 PV 列表
            values: 对应的当前值
        """
        self._initial_pvs = list(pvs)
        self._initial_values = list(values)

    def apply(self, pvs: list[str], values: list[float],
              clamp_fn=None) -> bool:
        """设置变量 PV 值（含安全验证）

        Args:
            pvs: 变量 PV 列表
            values: 目标值列表
            clamp_fn: 可选的裁剪函数

        Returns:
            bool: 是否全部设置成功

        Raises:
            RuntimeError: 写入失败且 rollback_on_failure=True
        """
        if clamp_fn:
            values = clamp_fn(values)

        elapsed = time.time() - self._last_adjust_time
        if elapsed < self.min_adjust_interval:
            wait = self.min_adjust_interval - elapsed
            print(f"  等待硬件调整间隔: {wait:.1f}秒")
            time.sleep(wait)

        pvs_list = list(pvs)
        values_list = list(values)
        for pv, val in zip(pvs_list, values_list):
            success = self._write_with_verify(pv, val)
            if not success:
                if self.rollback_on_failure:
                    self.rollback()
                    raise RuntimeError(
                        f"PV {pv} 写入失败（目标={val}），已回滚到初始值")
                return False

        all_settled, failed = self._wait_for_settled(pvs_list, values_list)
        if not all_settled:
            print(f"  警告: 以下设备未稳定: {list(failed.keys())}")

        self._last_adjust_time = time.time()
        return True

    def _write_with_verify(self, pv: str, value: float, retries: int = None) -> bool:
        """写入 PV 并读回验证"""
        retries = retries if retries is not None else self.write_retries
        for attempt in range(retries + 1):
            caput(pv, value, wait=True, timeout=max(1.0, self.max_wait))
            readback = caget(pv, timeout=1.0)
            if readback is not None and abs(readback - value) <= self.tolerance:
                return True
            if attempt < retries:
                print(f"  重试 {pv}: 设置={value:.4f} 读回={readback}")
                time.sleep(0.3 * (attempt + 1))
        return False

    def _wait_for_settled(self, pvs: list[str], targets: list[float]) -> tuple:
        """等待所有设备达到设定值"""
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > self.max_wait:
                readbacks = caget_many(pvs, timeout=1.0)
                failed = {}
                for pv, t, rb in zip(pvs, targets, readbacks):
                    if rb is None or abs(rb - t) > self.tolerance:
                        failed[pv] = {'target': t, 'readback': rb}
                return False, failed

            readbacks = caget_many(pvs, timeout=1.0)
            all_ok = True
            for pv, t, rb in zip(pvs, targets, readbacks):
                if rb is None or abs(rb - t) > self.tolerance:
                    all_ok = False
                    break
            if all_ok:
                return True, {}
            time.sleep(self.poll_interval)

    def rollback(self):
        """回滚到初始值"""
        if not self._initial_pvs or not self._initial_values:
            print("  警告: 没有可用的初始值用于回滚")
            return
        print("\n正在回滚到初始参数...")
        failed = 0
        for pv, val in zip(self._initial_pvs, self._initial_values):
            if not self._write_with_verify(pv, val):
                print(f"  警告: 回滚 {pv} 失败")
                failed += 1
        if failed:
            print(f"⚠ 回滚完成，{failed}/{len(self._initial_pvs)} 个 PV 失败")
        else:
            print("✓ 回滚完成")
