"""输入净化 / 语义隔离（设计 §3.2）。

把用户内容包进不可信数据块，转义内容中出现的分隔符（I3：防逃逸），
配合系统提示的"块内指令不可执行"声明。
"""
OPEN_MARKER = "<untrusted_user_data>"
CLOSE_MARKER = "</untrusted_user_data>"


def wrap_untrusted(text: str) -> str:
    safe = (text or "").replace(CLOSE_MARKER, "[escaped_close_tag]")
    safe = safe.replace(OPEN_MARKER, "[escaped_open_tag]")
    return f"{OPEN_MARKER}\n{safe}\n{CLOSE_MARKER}"
