"""目标函数基类模块

定义目标函数的统一接口。
"""
from abc import ABC, abstractmethod


class BaseObjective(ABC):
    """目标函数基类

    所有目标函数必须继承此类并实现 get_score 方法。
    """

    def __init__(self, config):
        """初始化目标函数

        Args:
            config: 配置字典，应包含：
                - objective.read_pvs: 读取的 PV 列表
                - objective.params: 目标函数专用参数
        """
        self.config = config
        self.read_pvs = config.get('objective', {}).get('read_pvs', [])
        self.params = config.get('objective', {}).get('params', {})

    @abstractmethod
    def get_score(self, params, device_pvs):
        """评估参数，返回评分（越小越好）

        Args:
            params: 要评估的参数列表
            device_pvs: 对应的设备 PV 列表

        Returns:
            float: 评分值，越小越好
        """
        pass

    def get_readings(self):
        """从 EPICS 读取数据

        Returns:
            list: PV 读数列表
        """
        from ..epics_backend import caget_many
        return caget_many(self.read_pvs)
