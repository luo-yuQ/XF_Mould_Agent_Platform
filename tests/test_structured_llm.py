from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agents.structured_llm import (
    JSON_MODE_INSTRUCTION,
    add_json_mode_instruction,
    ainvoke_structured_json,
    invoke_structured_json,
)


class FakeStructuredModel:
    def __init__(self, output):
        self.output = output
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return self.output

    async def ainvoke(self, messages):
        self.messages = messages
        return self.output


class FakeModel:
    def __init__(self, output):
        self.structured = FakeStructuredModel(output)
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        self.calls.append((schema, kwargs))
        return self.structured


def test_add_json_mode_instruction_extends_system_message_without_mutating_input():
    original = [SystemMessage(content="Follow the schema."), HumanMessage(content="go")]

    prepared = add_json_mode_instruction(original)

    assert prepared is not original
    assert original[0].content == "Follow the schema."
    assert JSON_MODE_INSTRUCTION in prepared[0].content


def test_add_json_mode_instruction_creates_system_message_when_missing():
    prepared = add_json_mode_instruction([HumanMessage(content="go")])

    assert isinstance(prepared[0], SystemMessage)
    assert JSON_MODE_INSTRUCTION in prepared[0].content


def test_invoke_structured_json_uses_json_mode_and_prepared_messages():
    schema = SimpleNamespace(name="schema")
    model = FakeModel({"ok": True})

    output = invoke_structured_json(model, schema, [HumanMessage(content="go")])

    assert output == {"ok": True}
    assert model.calls == [(schema, {"method": "json_mode"})]
    assert JSON_MODE_INSTRUCTION in model.structured.messages[0].content


@pytest.mark.asyncio
async def test_ainvoke_structured_json_uses_json_mode_and_prepared_messages():
    schema = SimpleNamespace(name="schema")
    model = FakeModel({"ok": True})

    output = await ainvoke_structured_json(
        model,
        schema,
        [HumanMessage(content="go")],
    )

    assert output == {"ok": True}
    assert model.calls == [(schema, {"method": "json_mode"})]
    assert JSON_MODE_INSTRUCTION in model.structured.messages[0].content
