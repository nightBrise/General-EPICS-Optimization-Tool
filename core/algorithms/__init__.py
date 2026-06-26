from .registry import register_algorithm, get_algorithm, list_algorithms
from . import de
from . import nelder_mead
from . import bayesian

try:
    from . import nevergrad
except ImportError:
    pass
