"""结构化 LLM 调用的轻量 JSON Mode 适配辅助函数。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage


JSON_MODE_INSTRUCTION = """你必须返回合法的 JSON。
只返回一个 JSON 对象。
不要输出 Markdown。
不要使用 ```json 代码块。
JSON 必须是整个响应的全部内容。
JSON 必须符合要求的 schema。"""


def add_json_mode_instruction(
    messages: Sequence[BaseMessage],
) -> list[BaseMessage]:
    """复制消息，并追加 provider 兼容的明确 JSON 输出指令。"""
    prepared = list(messages)
    for index, message in enumerate(prepared):
        if isinstance(message, SystemMessage):
            content = str(message.content)
            if JSON_MODE_INSTRUCTION not in content:
                prepared[index] = SystemMessage(
                    content=f"{content.rstrip()}\n\n{JSON_MODE_INSTRUCTION}",
                    additional_kwargs=dict(message.additional_kwargs),
                    response_metadata=dict(message.response_metadata),
                    name=message.name,
                    id=message.id,
                )
            return prepared

    return [SystemMessage(content=JSON_MODE_INSTRUCTION), *prepared]


def invoke_structured_json(
    model: Any,
    schema: Any,
    messages: Sequence[BaseMessage],
) -> Any:
    """使用 JSON Mode 和明确 JSON 指令同步调用结构化模型。"""
    structured_model = model.with_structured_output(schema, method="json_mode")
    return structured_model.invoke(add_json_mode_instruction(messages))


async def ainvoke_structured_json(
    model: Any,
    schema: Any,
    messages: Sequence[BaseMessage],
) -> Any:
    """使用 JSON Mode 和明确 JSON 指令异步调用结构化模型。"""
    structured_model = model.with_structured_output(schema, method="json_mode")
    return await structured_model.ainvoke(add_json_mode_instruction(messages))
