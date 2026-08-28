def calculator(expression: str) -> str:
    """
    安全计算基础数学表达式。
    """

    allowed = set("0123456789+-*/(). ")

    if not all(char in allowed for char in expression):
        return "计算表达式包含不允许的字符。"

    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"计算失败：{e}"
