"""后台优化线程管理

支持在后台线程中运行优化任务，并提供进度查询接口。
"""
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class OptimizationProgress:
    """优化进度数据"""
    running: bool = False
    iteration: int = 0
    budget: int = 0
    current_score: Optional[float] = None
    best_score: Optional[float] = None
    error: Optional[str] = None
    history: dict = field(default_factory=dict)


class OptimizationRunner:
    """后台优化线程管理器

    使用方法:
        runner = OptimizationRunner()
        runner.start(config, progress_callback=my_callback)
        # 轮询进度:
        progress = runner.get_progress()
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._progress = OptimizationProgress()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start(
        self,
        config: dict,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """启动优化（后台线程）

        Args:
            config: 优化配置字典
            progress_callback: 进度回调函数，签名: callback(iteration, budget, current_score, best_score)

        Returns:
            str: 状态消息
        """
        if self._progress.running:
            return "优化已在运行中"

        self._stop_event.clear()
        self._progress = OptimizationProgress(
            running=True,
            budget=config.get('optimization', {}).get('budget', 50)
        )

        self._thread = threading.Thread(
            target=self._run,
            args=(config, progress_callback)
        )
        self._thread.start()
        return "优化已启动..."

    def _run(self, config: dict, progress_callback: Optional[Callable]):
        """后台优化线程"""
        try:
            from core.objectives.registry import create_objective
            from core.optimizer import Optimizer

            objective_fn = create_objective(config)
            optimizer = Optimizer(config, objective_fn)

            def on_progress(iteration, bud, current_score, best_score):
                with self._lock:
                    self._progress.iteration = iteration
                    self._progress.current_score = current_score
                    self._progress.best_score = best_score
                if progress_callback:
                    progress_callback(iteration, bud, current_score, best_score)

            best_params, best_score, device_pvs, history = optimizer.run(
                progress_callback=on_progress
            )

            with self._lock:
                self._progress.history = history
                self._progress.best_score = best_score
                self._progress.running = False

        except Exception as e:
            with self._lock:
                self._progress.error = str(e)
                self._progress.running = False

    def stop(self):
        """停止优化"""
        self._stop_event.set()
        with self._lock:
            self._progress.running = False

    def get_progress(self) -> OptimizationProgress:
        """获取当前进度"""
        with self._lock:
            return self._progress
