"""Bounded, declarative subset of Algorithm Visualizer's command protocol."""
import math
import re

from .repository import AppError

TRACE_LIMIT = 4 * 1024 * 1024
MAX_COMMANDS = 40000
MAX_STEPS = 4000


def validate_trace(trace, source_lines):
    def require(condition, message):
        if not condition:
            raise AppError("演示步骤无效：" + message)

    def integer(value):
        return type(value) is int

    def scalar(value):
        return (value is None or type(value) is bool or
                isinstance(value, str) and len(value) <= 200 or
                type(value) is int and abs(value) <= 2**53 - 1 or
                type(value) is float and math.isfinite(value) and abs(value) <= 2**53 - 1)

    require(isinstance(trace, dict) and type(trace.get("version")) is int and trace.get("version") == 1 and trace.get("complete") is True,
            "缺少完整的版本 1 记录。")
    commands = trace.get("commands")
    require(isinstance(commands, list) and 0 < len(commands) <= MAX_COMMANDS, "命令数量超限或为空。")
    objects, root, steps = {}, None, 0
    types = {"Array1DTracer", "Array2DTracer", "LogTracer", "VerticalLayout", "HorizontalLayout"}
    for command in commands:
        require(isinstance(command, dict), "命令必须是对象。")
        key, method, args = (command.get(field) for field in ("key", "method", "args"))
        require(isinstance(method, str) and isinstance(args, list), "命令方法或参数格式错误。")
        if key is None:
            if method == "setRoot":
                require(len(args) == 1 and isinstance(args[0], str) and args[0] in objects, "布局根节点不存在。")
                root = args[0]
            elif method == "delay":
                require(root is not None, "必须先设置展示布局。")
                require(1 <= len(args) <= 2 and integer(args[0]) and 1 <= args[0] <= source_lines, "源码行号越界。")
                if len(args) == 2:
                    meta = args[1]
                    require(isinstance(meta, dict), "步骤说明必须是对象。")
                    require(isinstance(meta.get("message", ""), str) and len(meta.get("message", "")) <= 4000, "说明过长或格式错误。")
                    require(isinstance(meta.get("kind", ""), str), "步骤类型格式错误。")
                    require(isinstance(meta.get("state", {}), dict), "变量状态格式错误。")
                    pairs = meta.get("pairs", [])
                    require(isinstance(pairs, list) and len(pairs) <= 20 and all(isinstance(p, list) and len(p) == 2 and all(scalar(x) for x in p) for p in pairs), "配对数据格式错误。")
                    for field in ("before", "after"):
                        require(field not in meta or integer(meta[field]) and abs(meta[field]) <= 2**53 - 1, "计数超限或格式错误。")
                steps += 1
                require(steps <= MAX_STEPS, "超过 4000 步，请缩小输入。")
            else:
                raise AppError("演示步骤无效：不支持的全局命令。")
            continue
        require(isinstance(key, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", key) is not None, "对象编号格式错误。")
        if method in types:
            require(key not in objects and len(objects) < 32, "对象重复或超过 32 个。")
            require(len(args) == 1, "对象构造参数错误。")
            if method.endswith("Layout"):
                require(isinstance(args[0], list) and len(args[0]) <= 32 and all(isinstance(x, str) and x in objects for x in args[0]), "布局包含不存在的对象。")
            else:
                require(isinstance(args[0], str) and len(args[0]) <= 200, "对象标题格式错误。")
            objects[key] = {"type": method, "shape": [], "length": 0}
            continue
        require(key in objects, "对象不存在。")
        obj = objects[key]
        if obj["type"] == "LogTracer":
            require(method in ("set", "print", "println") and len(args) == 1 and isinstance(args[0], str), "文字日志命令错误。")
            obj["length"] = (0 if method == "set" else obj["length"]) + len(args[0]) + (method == "println")
            require(obj["length"] <= 20000, "文字日志过长。")
            continue
        require(obj["type"] in ("Array1DTracer", "Array2DTracer"), "不支持的布局修改命令。")
        one = obj["type"] == "Array1DTracer"
        if method == "set":
            require(len(args) == 1 and isinstance(args[0], list), "数组赋值格式错误。")
            rows = [args[0]] if one else args[0]
            require(len(rows) <= 32 and all(isinstance(row, list) and len(row) <= 128 and all(scalar(x) for x in row) for row in rows), "数组值或规模无效。")
            require(sum(map(len, rows)) <= 512, "展示数组超过 512 个单元格。")
            obj["shape"] = [len(row) for row in rows]
            continue
        shape = obj["shape"]
        def position(x, y):
            return integer(x) and integer(y) and 0 <= x < len(shape) and 0 <= y < shape[x]
        if method in ("patch", "depatch"):
            size = 1 if one else 2
            require(len(args) in ([size, size + 1] if method == "patch" else [size]), "数组更新参数错误。")
            x, y = (0, args[0]) if one else args[:2]
            require(position(x, y), "数组更新位置越界。")
            require(len(args) == size or scalar(args[-1]), "数组更新值无效。")
        elif method in ("select", "deselect"):
            require(len(args) in ([1, 2] if one else [2, 4]), "选择范围参数错误。")
            if one:
                sx = ex = 0
                sy, ey = args[0], args[-1]
            else:
                sx, sy = args[:2]
                ex, ey = args[2:] if len(args) == 4 else args[:2]
            require(position(sx, sy) and position(ex, ey) and sx <= ex and sy <= ey and all(position(x, ey) for x in range(sx, ex + 1)), "数组选择范围越界。")
        else:
            raise AppError(f"演示步骤无效：不支持数组命令 {method}。")
    require(steps > 0 and commands[-1].get("key") is None and commands[-1].get("method") == "delay", "最后一步不完整。")
    return steps
