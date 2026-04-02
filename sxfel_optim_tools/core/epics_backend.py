"""统一的 EPICS 后端选择器

支持运行时在模拟器和真实 EPICS 之间切换。

使用方法:
    from core.epics_backend import set_backend, caget, caput

    # 设置使用模拟器（默认）
    set_backend(use_simulator=True)

    # 设置使用真实 EPICS
    set_backend(use_simulator=False)

    # 之后调用 caget/caput 会自动路由到正确的后端
"""
import threading
import time
from typing import Optional, List, Tuple


# ============ EPICS 异常类 ============

class EPICSError(Exception):
    """EPICS 操作异常基类"""
    pass

class PVConnectionError(EPICSError):
    """PV 连接失败"""
    pass

class PVTimeoutError(EPICSError):
    """PV 操作超时"""
    pass

class PVWriteError(EPICSError):
    """PV 写入失败"""
    pass


# ============ 重试机制参数 ============

MAX_RETRIES = 5
RETRY_DELAY_START = 1.0  # 秒
RETRY_DELAY_INCREMENT = 1.0  # 每次增加的秒数


class EPICSBackend:
    """EPICS 后端选择器（单例模式）

    支持运行时在模拟器和真实 EPICS 之间切换。
    所有 caget/caput 调用通过此类分派到正确的后端。
    """
    _instance: Optional['EPICSBackend'] = None
    _lock = threading.Lock()
    _use_simulator: bool = True  # 默认使用模拟器

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._simulator = None
        self._epics_module = None

    @classmethod
    def set_backend(cls, use_simulator: bool) -> None:
        """设置后端模式

        Args:
            use_simulator: True=使用模拟器, False=使用真实 EPICS
        """
        with cls._lock:
            cls._use_simulator = use_simulator
            # 重置模块引用，迫使其在下次使用时重新导入
            cls._instance._epics_module = None

    @classmethod
    def is_simulator(cls) -> bool:
        """返回当前是否使用模拟器"""
        return cls._use_simulator

    @classmethod
    def get_instance(cls) -> 'EPICSBackend':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_simulator(self):
        """获取模拟器实例（延迟导入）"""
        if self._simulator is None:
            from .simulator import SimpleEPICSSimulator
            self._simulator = SimpleEPICSSimulator()
        return self._simulator

    def _get_epics(self):
        """获取 EPICS 模块（延迟导入）"""
        if self._epics_module is None:
            import epics
            self._epics_module = epics
        return self._epics_module

    def _caget_impl(self, pv: str, timeout: float = 1.0):
        """caget 实现（不分派后端）

        Args:
            pv: PV 名称
            timeout: 超时时间（秒）

        Returns:
            PV 值，失败返回 None
        """
        if self._use_simulator:
            return self._get_simulator().caget(pv, timeout)
        else:
            epics = self._get_epics()
            return epics.caget(pv, timeout=timeout)

    def caget(self, pv: str, timeout: float = 1.0):
        """读取 PV 值（带重试机制）

        Args:
            pv: PV 名称
            timeout: 超时时间（秒）

        Returns:
            PV 值

        Raises:
            PVConnectionError: 连接失败或超时
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                value = self._caget_impl(pv, timeout)
                if value is not None:
                    return value
                last_error = f"PV {pv} 返回 None"
            except Exception as e:
                last_error = f"PV {pv} 异常: {str(e)}"

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_START + attempt * RETRY_DELAY_INCREMENT
                print(f"  警告: {last_error}，{delay:.1f}秒后重试...")
                time.sleep(delay)

        raise PVConnectionError(f"PV {pv} 连接失败，已重试 {MAX_RETRIES} 次: {last_error}")

    def caput(self, pv: str, value, wait: bool = False, timeout: float = 1.0) -> bool:
        """设置 PV 值

        Args:
            pv: PV 名称
            value: 要设置的值
            wait: 是否等待完成
            timeout: 超时时间（秒）

        Returns:
            成功返回 True，失败返回 False

        Raises:
            PVWriteError: 写入失败（仅在模拟器模式抛出）
        """
        if self._use_simulator:
            result = self._get_simulator().caput(pv, value, wait, timeout)
            if not result:
                raise PVWriteError(f"PV {pv} 写入失败")
            return result
        else:
            epics = self._get_epics()
            epics.caput(pv, value, wait=wait, timeout=timeout)
            return True

    def _caput_impl(self, pv: str, value, wait: bool = False, timeout: float = 1.0) -> bool:
        """caput 实现（不分派后端）"""
        if self._use_simulator:
            return self._get_simulator().caput(pv, value, wait, timeout)
        else:
            epics = self._get_epics()
            epics.caput(pv, value, wait=wait, timeout=timeout)
            return True

    def caget_many(self, pvs: List[str], timeout: float = 1.0) -> List:
        """批量读取 PV 值（带重试机制）

        Args:
            pvs: PV 名称列表
            timeout: 超时时间（秒）

        Returns:
            PV 值列表（包含 None 表示该 PV 读取失败）
        """
        results = []
        for pv in pvs:
            try:
                value = self.caget(pv, timeout)
                results.append(value)
            except PVConnectionError:
                # 连接失败时继续处理其他 PV
                results.append(None)
        return results

    def caput_many(self, pvs: List[str], values: List, wait: bool = False, timeout: float = 1.0) -> bool:
        """批量设置 PV 值

        Args:
            pvs: PV 名称列表
            values: 要设置的值列表
            wait: 是否等待完成
            timeout: 超时时间（秒）

        Returns:
            成功返回 True，失败返回 False
        """
        if self._use_simulator:
            return self._get_simulator().caput_many(pvs, values, wait, timeout)
        else:
            epics = self._get_epics()
            for pv, value in zip(pvs, values):
                epics.caput(pv, value, wait=wait, timeout=timeout)
            return True


# 创建全局后端实例
_backend = EPICSBackend()


# ============ 便捷函数接口 ============

def set_backend(use_simulator: bool) -> None:
    """设置后端模式（模块级函数）"""
    EPICSBackend.set_backend(use_simulator)


def is_simulator() -> bool:
    """返回当前是否使用模拟器"""
    return EPICSBackend.is_simulator()


def caget(pv: str, timeout: float = 1.0):
    """读取 PV 值"""
    return _backend.caget(pv, timeout)


def caput(pv: str, value, wait: bool = False, timeout: float = 1.0) -> bool:
    """设置 PV 值"""
    return _backend.caput(pv, value, wait, timeout)


def caget_many(pvs: List[str], timeout: float = 1.0) -> List:
    """批量读取 PV 值"""
    return _backend.caget_many(pvs, timeout)


def caput_many(pvs: List[str], values: List, wait: bool = False, timeout: float = 1.0) -> bool:
    """批量设置 PV 值"""
    return _backend.caput_many(pvs, values, wait, timeout)
