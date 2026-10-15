"""输入净化 / 语义隔离（设计 §3.2）。

把用户内容包进不可信数据块，配合系统提示的"块内指令不可执行"声明。
"""
OPEN_MARKER = "<untrusted_user_data>"
CLOSE_MARKER = "</untrusted_user_data>"


def wrap_untrusted(text: str) -> str:
    return f"{OPEN_MARKER}\n{text}\n{CLOSE_MARKER}"
