import unittest
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

try:
    import langchain_openai  # noqa: F401
except ModuleNotFoundError:
    langchain_openai_stub = ModuleType("langchain_openai")

    class ChatOpenAIStub:
        def __init__(self, *args, **kwargs):
            pass

        def with_structured_output(self, *args, **kwargs):
            raise NotImplementedError

        async def ainvoke(self, *args, **kwargs):
            raise NotImplementedError

        def astream(self, *args, **kwargs):
            raise NotImplementedError

    langchain_openai_stub.ChatOpenAI = ChatOpenAIStub
    sys.modules["langchain_openai"] = langchain_openai_stub

from agents import supervisor


async def _unused_node(state):
    return state


_agent_modules = {}
for _module_name, _functions in {
    "agents.rd_agent": ("rd_rag_node", "rd_writer_node"),
    "agents.quality_agent": ("qa_rag_node", "qa_writer_node"),
    "agents.chat_agent": ("chat_chat_node",),
}.items():
    _agent_modules[_module_name] = sys.modules.get(_module_name)
    _module = ModuleType(_module_name)
    for _function_name in _functions:
        setattr(_module, _function_name, _unused_node)
    sys.modules[_module_name] = _module

import graph as graph_module

for _module_name, _original_module in _agent_modules.items():
    if _original_module is None:
        sys.modules.pop(_module_name, None)
    else:
        sys.modules[_module_name] = _original_module


def _base_state(**overrides):
    state = {
        "messages": [HumanMessage(content="测试问题", name="user")],
        "sender": "user",
        "next_agent": "",
        "intent": "",
        "agent_override": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
    }
    state.update(overrides)
    return state


class SupervisorDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_decisions_freeze_rd_quality_and_chat(self):
        for next_agent in ("rd", "quality", "chat"):
            with self.subTest(next_agent=next_agent):
                structured_llm = MagicMock()
                structured_llm.ainvoke = AsyncMock(
                    return_value=supervisor.RouteDecision(
                        reasoning=f"route to {next_agent}",
                        next_agent=next_agent,
                        intent=f"{next_agent}_intent",
                    )
                )
                fake_llm = MagicMock()
                fake_llm.with_structured_output.return_value = structured_llm

                with patch.object(supervisor, "LLM", fake_llm):
                    result = await supervisor.supervisor_node(_base_state())

                self.assertEqual(result["next_agent"], next_agent)
                self.assertEqual(result["intent"], f"{next_agent}_intent")
                self.assertEqual(result["sender"], "supervisor")
                self.assertFalse(result["task_completed"])
                fake_llm.with_structured_output.assert_called_once_with(
                    supervisor.RouteDecision
                )
                structured_llm.ainvoke.assert_awaited_once()

    async def test_manual_rd_and_quality_overrides_do_not_call_llm(self):
        for override in ("rd", "quality"):
            with self.subTest(override=override):
                fake_llm = MagicMock()
                fake_llm.ainvoke = AsyncMock()

                with patch.object(supervisor, "LLM", fake_llm):
                    result = await supervisor.supervisor_node(
                        _base_state(agent_override=override)
                    )

                self.assertEqual(result["next_agent"], override)
                self.assertEqual(result["intent"], f"user_override_{override}")
                self.assertEqual(result["agent_override"], override)
                fake_llm.with_structured_output.assert_not_called()
                fake_llm.ainvoke.assert_not_awaited()

    async def test_unparseable_structured_and_raw_outputs_default_to_rd(self):
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=ValueError("bad structured output"))
        fake_llm = MagicMock()
        fake_llm.with_structured_output.return_value = structured_llm
        fake_llm.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content="not json")
        )

        with patch.object(supervisor, "LLM", fake_llm):
            result = await supervisor.supervisor_node(_base_state())

        self.assertEqual(result["next_agent"], "rd")
        self.assertEqual(result["intent"], "default")
        fake_llm.ainvoke.assert_awaited_once()


class SupervisorGraphRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_next_agent_enters_expected_graph_branch(self):
        expected_branch = {
            "rd": "rd_rag",
            "quality": "qa_rag",
            "chat": "chat_chat",
        }

        for next_agent, branch_name in expected_branch.items():
            with self.subTest(next_agent=next_agent):
                visited = []

                async def supervisor_stub(state):
                    visited.append("supervisor")
                    return {
                        **state,
                        "sender": "supervisor",
                        "next_agent": next_agent,
                        "intent": f"{next_agent}_intent",
                    }

                async def rd_rag_stub(state):
                    visited.append("rd_rag")
                    return {**state, "sender": "rd_rag"}

                async def rd_writer_stub(state):
                    visited.append("rd_writer")
                    return {**state, "sender": "rd_writer", "task_completed": True}

                async def qa_rag_stub(state):
                    visited.append("qa_rag")
                    return {**state, "sender": "qa_rag"}

                async def qa_writer_stub(state):
                    visited.append("qa_writer")
                    return {**state, "sender": "qa_writer", "task_completed": True}

                async def chat_stub(state):
                    visited.append("chat_chat")
                    return {**state, "sender": "chat_chat", "task_completed": True}

                with patch.multiple(
                    graph_module,
                    supervisor_node=supervisor_stub,
                    rd_rag_node=rd_rag_stub,
                    rd_writer_node=rd_writer_stub,
                    qa_rag_node=qa_rag_stub,
                    qa_writer_node=qa_writer_stub,
                    chat_chat_node=chat_stub,
                ):
                    workflow = graph_module.build_graph()
                    result = await workflow.ainvoke(_base_state())

                self.assertEqual(visited[0], "supervisor")
                self.assertIn(branch_name, visited)
                self.assertEqual(result["next_agent"], next_agent)
                if next_agent == "rd":
                    self.assertEqual(visited, ["supervisor", "rd_rag", "rd_writer"])
                elif next_agent == "quality":
                    self.assertEqual(visited, ["supervisor", "qa_rag", "qa_writer"])
                else:
                    self.assertEqual(visited, ["supervisor", "chat_chat"])


if __name__ == "__main__":
    unittest.main()
