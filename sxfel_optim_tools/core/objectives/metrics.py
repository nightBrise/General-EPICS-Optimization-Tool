"""优化指标追踪器模块

提供线程安全的指标追踪功能。
"""
import threading


class MetricsTracker:
    """线程安全的指标追踪器

    使用单例模式确保全局只有一个实例。
    """

    _instance = None
    _lock = threading.Lock()

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
        self._current = {}
        self._best = {}
        self._best_score = float('inf')
        self._initialized = True

    def get_current(self):
        """获取当前指标副本"""
        return self._current.copy()

    def get_best(self):
        """获取最佳指标副本"""
        return self._best.copy()

    def update(self, current, score):
        """更新当前指标，如果改进则更新最佳

        Args:
            current: 当前指标字典
            score: 当前评分

        Returns:
            bool: 是否为新最佳
        """
        self._current = current.copy()
        if score < self._best_score:
            self._best_score = score
            self._best = current.copy()
            return True
        return False

    def reset(self):
        """重置所有指标"""
        self._current = {}
        self._best = {}
        self._best_score = float('inf')

    @property
    def best_score(self):
        """获取最佳评分"""
        return self._best_score


# 全局实例
metrics = MetricsTracker()
