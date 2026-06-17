"""工具函数：配置加载与验证"""
import re
import json


def load_generic_config(config_file: str) -> dict:
    """加载通用优化器配置文件（支持 // 和 # 注释）

    Args:
        config_file: JSON 配置文件路径

    Returns:
        dict: 解析后的配置字典

    Raises:
        json.JSONDecodeError: JSON 格式错误
        FileNotFoundError: 文件不存在
    """
    with open(config_file, 'r') as f:
        text = f.read()
    text = re.sub(r'(?m)^\s*//.*$', '', text)      # 整行 // 注释
    text = re.sub(r'(?m)^\s*#.*$', '', text)       # 整行 # 注释
    text = re.sub(r'(?m)[ \t]+//.*$', '', text)    # 行尾 // 注释
    text = re.sub(r'(?m)[ \t]+#.*$', '', text)     # 行尾 # 注释
    return json.loads(text)


def validate_generic_config(config: dict) -> tuple[list[str], list[str]]:
    """验证通用优化器配置

    Args:
        config: 配置字典

    Returns:
        tuple[list[str], list[str]]: (errors, warnings)
            errors 不为空时配置无效，不应继续运行
            warnings 为提示性建议，不影响运行
    """
    errors = []
    warnings = []

    if not config.get('variables'):
        errors.append("未配置 variables（变量 PV）")
    else:
        for i, v in enumerate(config['variables']):
            if 'pv' not in v:
                errors.append(f"variables[{i}] 缺少 pv 字段")
            if 'range' not in v or len(v.get('range', [])) != 2:
                errors.append(f"variables[{i}] ({v.get('pv', '?')}) 缺少有效的 range")

    obj = config.get('objectives', {})
    groups = obj.get('groups', [])
    if not groups:
        errors.append("未配置 objectives.groups（目标 PV）")
    for gi, g in enumerate(groups):
        if not g.get('pvs'):
            errors.append(f"objectives.groups[{gi}] 缺少 pvs")
        for pi, pv in enumerate(g.get('pvs', [])):
            if isinstance(pv, str):
                continue
            if 'pv' not in pv:
                errors.append(f"objectives.groups[{gi}].pvs[{pi}] 缺少 pv 字段")

    opt = config.get('optimization', {})
    if not opt.get('budget'):
        warnings.append("未设置 optimization.budget，将使用默认值 50")

    return errors, warnings
