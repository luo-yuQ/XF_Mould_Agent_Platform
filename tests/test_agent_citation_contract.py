import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage


try:
    import langchain_openai  # noqa: F401
except ModuleNotFoundError:
    langchain_openai_stub = ModuleType("langchain_openai")

    class ChatOpenAIStub:
        def __init__(self, *args, **kwargs):
            pass

        def astream(self, *args, **kwargs):
            raise NotImplementedError

        def with_structured_output(self, *args, **kwargs):
            raise NotImplementedError

        async def ainvoke(self, *args, **kwargs):
            raise NotImplementedError

    langchain_openai_stub.ChatOpenAI = ChatOpenAIStub
    sys.modules["langchain_openai"] = langchain_openai_stub


_original_rag_module = sys.modules.get("tools.rag")
rag_stub = ModuleType("tools.rag")
rag_stub.retrieve_structured = MagicMock(
    side_effect=AssertionError("citation contract tests must not call Milvus")
)
rag_stub.chunks_to_text = lambda chunks: "\n".join(
    str(chunk.get("text", "")) for chunk in chunks
)
sys.modules["tools.rag"] = rag_stub

from agents import quality_agent, rd_agent

if _original_rag_module is None:
    sys.modules.pop("tools.rag", None)
else:
    sys.modules["tools.rag"] = _original_rag_module


CITATION_FIELDS = {
    "source",
    "chapter",
    "section_title",
    "heading_path",
    "chunk_type",
    "table_id",
    "row_range",
    "chunk_uid",
    "parent_chunk_uid",
}


def _state(rag_chunks):
    return {
        "messages": [HumanMessage(content="请分析当前问题", name="user")],
        "sender": "user",
        "next_agent": "",
        "intent": "",
        "agent_override": "",
        "rag_result": "retrieved text" if rag_chunks else "",
        "rag_chunks": rag_chunks,
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
    }


def _chunks():
    return [
        {
            "text": "first reference",
            "doc_source": "manual-a.pdf",
            "doc_chapter": "1",
            "doc_section": "section-a",
            "heading_path": "1 > section-a",
            "chunk_type": "text",
            "table_id": "",
            "row_range": "",
            "chunk_uid": "chunk-a",
            "parent_chunk_uid": "",
        },
        {
            "text": "second reference",
            "doc_source": "manual-b.pdf",
            "doc_chapter": "2",
            "doc_section": "section-b",
            "heading_path": "2 > section-b",
            "chunk_type": "table_row_block",
            "table_id": "table-2",
            "row_range": "1-3",
            "chunk_uid": "chunk-b",
            "parent_chunk_uid": "table-parent",
        },
    ]


def _streaming_result(*parts):
    async def stream(*args, **kwargs):
        for part in parts:
            yield SimpleNamespace(content=part)

    return stream


def _fake_streaming_llm(*parts):
    return SimpleNamespace(astream=_streaming_result(*parts))


class AgentCitationContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_rd_and_quality_use_the_same_citation_metadata_fields(self):
        chunks = _chunks()
        quality_payload = json.dumps(
            {"answer": "质量结论 [1] [2]", "citation_ids": [1, 2]},
            ensure_ascii=False,
        )

        with patch.object(
            rd_agent,
            "llm",
            _fake_streaming_llm("研发结论 [1] [2]"),
        ):
            rd_result = await rd_agent.rd_writer_node(_state(chunks))

        with patch.object(
            quality_agent,
            "llm",
            _fake_streaming_llm(quality_payload),
        ):
            quality_result = await quality_agent.qa_writer_node(_state(chunks))

        self.assertEqual(set(rd_result["citation_map"][1]), CITATION_FIELDS)
        self.assertEqual(set(quality_result["citation_map"][1]), CITATION_FIELDS)
        self.assertEqual(
            set(rd_result["citation_map"][1]),
            set(quality_result["citation_map"][1]),
        )

    async def test_rd_filters_duplicate_out_of_range_and_illegal_markers(self):
        with patch.object(
            rd_agent,
            "llm",
            _fake_streaming_llm(
                "结论 [2]，重复 [2]，有效 [1]，越界 [99]，非法 [-1] [abc]。"
            ),
        ):
            result = await rd_agent.rd_writer_node(_state(_chunks()))

        self.assertEqual(result["citation_ids"], [1, 2])
        self.assertEqual(set(result["citation_map"]), {1, 2})
        self.assertTrue(result["rag_is_relevant"])

    async def test_quality_filters_out_of_range_and_illegal_ids(self):
        payload = json.dumps(
            {
                "answer": "质量结论 [2] [1] [99]",
                "citation_ids": [2, 99, -1, "1", "bad", 1],
            },
            ensure_ascii=False,
        )
        with patch.object(
            quality_agent,
            "llm",
            _fake_streaming_llm(payload),
        ):
            result = await quality_agent.qa_writer_node(_state(_chunks()))

        self.assertEqual(result["citation_ids"], [2, 1])
        self.assertEqual(set(result["citation_map"]), {1, 2})
        self.assertTrue(result["rag_is_relevant"])

    async def test_no_retrieval_results_produce_empty_citations(self):
        quality_payload = json.dumps(
            {"answer": "无检索材料的质量回答", "citation_ids": []},
            ensure_ascii=False,
        )

        with patch.object(
            rd_agent,
            "llm",
            _fake_streaming_llm("无检索材料的研发回答"),
        ):
            rd_result = await rd_agent.rd_writer_node(_state([]))

        with patch.object(
            quality_agent,
            "llm",
            _fake_streaming_llm(quality_payload),
        ):
            quality_result = await quality_agent.qa_writer_node(_state([]))

        for result in (rd_result, quality_result):
            self.assertEqual(result["citation_map"], {})
            self.assertEqual(result["citation_ids"], [])
            self.assertFalse(result["rag_is_relevant"])

    async def test_current_writer_identity_and_completion_fields_are_frozen(self):
        quality_payload = json.dumps(
            {"answer": "质量回答 [1]", "citation_ids": [1]},
            ensure_ascii=False,
        )

        with patch.object(
            rd_agent,
            "llm",
            _fake_streaming_llm("研发回答 [1]"),
        ):
            rd_result = await rd_agent.rd_writer_node(_state(_chunks()))

        with patch.object(
            quality_agent,
            "llm",
            _fake_streaming_llm(quality_payload),
        ):
            quality_result = await quality_agent.qa_writer_node(_state(_chunks()))

        self.assertEqual(rd_result["sender"], "rd_writer")
        self.assertEqual(rd_result["messages"][-1].name, "rd_agent")
        self.assertTrue(rd_result["task_completed"])

        self.assertEqual(quality_result["sender"], "qa_writer")
        self.assertEqual(quality_result["messages"][-1].name, "quality_agent")
        self.assertTrue(quality_result["task_completed"])


if __name__ == "__main__":
    unittest.main()
