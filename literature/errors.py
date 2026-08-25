# literature/errors.py
# 文献检索错误类型：必须区分"API 不可用/超时/限速/解析失败/无结果"，
# 绝不把 API 故障静默伪装成"没有相关论文"。

from __future__ import annotations

from typing import Optional


class LiteratureSearchError(Exception):
    """文献检索错误基类。

    kind ∈ {"api_unavailable", "timeout", "rate_limited", "parsing", "invalid_input"}
    """

    def __init__(self, kind: str, message: str, *, status_code: Optional[int] = None, source: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status_code = status_code
        self.source = source

    def to_user_message(self) -> str:
        """面向用户的明确提示（不把 API 故障说成无结果）。"""
        if self.kind == "timeout":
            return "文献检索超时，服务暂时不可用。"
        if self.kind == "rate_limited":
            return "文献检索请求过于频繁，请稍后重试。"
        if self.kind == "parsing":
            return "文献检索返回数据解析失败，服务可能异常。"
        if self.kind == "invalid_input":
            return f"检索参数无效: {self.message}"
        # api_unavailable / 其他
        return "文献检索服务暂时不可用。"


class NoRelevantResults(LiteratureSearchError):
    """API 正常返回但没有任何相关结果 —— 与 API 故障严格区分。"""

    def __init__(self, message: str = "未检索到相关文献"):
        super().__init__("no_result", message, status_code=None, source="")


def unavailable(source: str, detail: str, status_code: Optional[int] = None) -> LiteratureSearchError:
    return LiteratureSearchError("api_unavailable", f"[{source}] {detail}", status_code=status_code, source=source)
