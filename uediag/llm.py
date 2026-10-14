"""模型客户端：文本（规划）+ 视觉（只读图出结构化信息）。

对外：
    chat(messages, tools=None, ...)     一次对话补全，自动记账
    describe_image(path, question)      单轮视觉抽取（视觉模型不参与规划）
    as_message_dict(message)            把 SDK 的 assistant 消息转成可回传的 dict
    usage() / reset_usage()             token 与花费统计

约定：图片永远不出现在主循环里，只在 describe_image 这一次子请求里出现。
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

from uediag.types import cfg, load_prompt, require_api_key

# 价格表（元 / 百万 token），按模型名覆盖；缺省用 DEFAULT_PRICE。
# 单价随时会变，改这里就行；成本只用于演示时「这次花了多少钱」。
DEFAULT_PRICE = (1.0, 4.0)          # (输入, 输出)
PRICES: dict[str, tuple[float, float]] = {}

USAGE: dict[str, float] = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}

_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=require_api_key(), base_url=cfg("OPENAI_API_URL"))
    return _client


def chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    model: str | None = None,
    tool_choice: Any = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    thinking: str | None = None,
):
    """一次 chat.completions 调用，返回 message 对象（不是整个 response）。

    思考模式的坑（官方文档 + 实测）：
    - 默认**打开**，且此时**不支持指定函数的 tool_choice**（会 400 "Thinking mode does not support this tool_choice"）
    - 带 tools 的请求，后续每一轮**必须回传 reasoning_content**，否则 400（见 as_message_dict）
    - 思考模式下 temperature 被忽略
    所以默认走 `THINKING=disabled`：可强制 finish、可复现、更快更便宜。
    """
    kwargs: dict[str, Any] = {"model": model or cfg("MODEL_TEXT"), "messages": messages}
    if tools:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    mode = (thinking or cfg("THINKING")).strip().lower()
    kwargs["extra_body"] = {"thinking": {"type": "enabled" if mode == "enabled" else "disabled"}}
    if mode == "enabled":
        kwargs["reasoning_effort"] = cfg("REASONING_EFFORT")

    resp = client().chat.completions.create(**kwargs)
    _account(kwargs["model"], getattr(resp, "usage", None))
    return resp.choices[0].message


def describe_image(path: str | Path, question: str) -> str:
    """视觉抽取：图 + 问题 → 纯文本。视觉模型只做感知，禁止推理（见 prompts/vision_extract.md）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"截图不存在: {path}")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    instruction = load_prompt("vision_extract") or "只抽取图片里的客观信息，不要推断根因，不要给修复建议。"
    msg = chat(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{instruction}\n\n需要重点看的是：{question}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}", "detail": cfg("VISION_DETAIL")},
                    },
                ],
            }
        ],
        model=cfg("MODEL_VISION"),
        temperature=0,
    )
    return (msg.content or "").strip()


def as_message_dict(message) -> dict:
    """assistant 消息必须原样回传（含 tool_calls / reasoning_content），否则下一轮请求会 400。

    - tool_calls：不带上，后面的 role="tool" 消息就没有可配对的对象
    - reasoning_content：**带 tools 的请求，思考模式下必须完整回传**，漏了直接 400
    """
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        out["reasoning_content"] = reasoning
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
            }
            for tc in tool_calls
        ]
    return out


def tool_args(tool_call) -> dict:
    """安全解析工具参数：模型给的 arguments 是 JSON 字符串，可能不合法。"""
    import json

    try:
        args = json.loads(tool_call.function.arguments or "{}")
        return args if isinstance(args, dict) else {}
    except json.JSONDecodeError:
        return {}


def tool_reply(tool_call_id: str, content: str) -> dict:
    """构造一条 role=tool 的回复；tool_call_id 必须与请求一一对应。"""
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def usage() -> dict:
    return dict(USAGE)


def reset_usage() -> None:
    for k in USAGE:
        USAGE[k] = 0


def _account(model: str, u) -> None:
    if u is None:
        return
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    tin = getattr(u, "prompt_tokens", 0) or 0
    tout = getattr(u, "completion_tokens", 0) or 0
    USAGE["calls"] += 1
    USAGE["in"] += tin
    USAGE["out"] += tout
    USAGE["cost"] += (tin * pin + tout * pout) / 1_000_000


class Timer:
    """with Timer() as t: ... → t.ms"""

    def __enter__(self):
        self._t0 = time.perf_counter()
        self.ms = 0
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t0) * 1000)
        return False
