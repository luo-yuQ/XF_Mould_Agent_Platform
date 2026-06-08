import copy
import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import BusinessArtifactVersion, ChatSession, FMEARun, User
from models.base import Base
from services.artifact_revision_service import (
    ArtifactRevisionError,
    create_initial_fmea_version,
    get_artifact_version,
    list_artifact_versions,
    list_session_artifacts,
    revise_artifact_version,
)


def _row(row_id: int, action: str) -> dict:
    return {
        "id": row_id,
        "function": "保证冲压边缘质量",
        "requirement": "毛刺高度受控",
        "failure_mode": f"边缘毛刺-{row_id}",
        "effect": "装配干涉",
        "severity": {
            "value": 6,
            "suggested": True,
            "rationale": "依据现场风险评估",
        },
        "cause": "模具间隙偏大",
        "occurrence": {
            "value": 4,
            "suggested": True,
            "rationale": "依据历史发生频次",
        },
        "prevention_control": "换模后确认模具间隙",
        "detection_control": "巡检毛刺高度",
        "detection": {
            "value": 4,
            "suggested": True,
            "rationale": "依据当前巡检能力",
        },
        "action_priority": {
            "value": "M",
            "suggested": True,
            "rationale": "依据 S/O/D 综合判断",
        },
        "rpn": 96,
        "recommended_action": action,
        "evidence": "现场风险评估，评分需人工确认",
    }


def _output(action_prefix: str) -> dict:
    return {
        "rows": [
            _row(index, f"{action_prefix}，记录结果并由质量工程师当班确认")
            for index in range(1, 4)
        ]
    }


class FakeLLM:
    def __init__(self, outputs: list[dict | str]):
        self.outputs = list(outputs)
        self.calls = 0

    async def ainvoke(self, messages):
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return SimpleNamespace(content=content)


class ArtifactRevisionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        self.user = User(username="revision-user", password_hash="test")
        self.db.add(self.user)
        self.db.flush()
        self.session = ChatSession(
            id="revision-session",
            user_id=self.user.id,
            title="revision test",
        )
        self.db.add(self.session)
        self.db.flush()

        self.input_json = {
            "fmea_type": "PFMEA",
            "product": "座椅滑轨",
            "process": "冲压",
            "failure_phenomenon": "毛刺超标",
            "background": "",
        }
        self.references = [{"source_id": "1", "source": "FMEA手册.pdf"}]
        self.run = FMEARun(
            user_id=self.user.id,
            session_id=self.session.id,
            artifact_type="fmea_run",
            product="座椅滑轨",
            process="冲压",
            failure_phenomenon="毛刺超标",
            input_json=self.input_json,
            output_json=_output("检查毛刺高度"),
            output_markdown="# PFMEA V1",
            references_json=self.references,
        )
        self.db.add(self.run)
        self.db.flush()
        self.v1 = create_initial_fmea_version(self.db, self.run)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    async def test_revision_creates_new_version_and_preserves_base(self):
        old_output = copy.deepcopy(self.v1.output_json)
        llm = FakeLLM([_output("每班首件和末件检查并测量毛刺高度")])

        result = await revise_artifact_version(
            self.db,
            artifact_id=self.run.id,
            artifact_type="fmea",
            base_version_id=self.v1.id,
            revision_instruction="把建议措施写得更具体",
            created_by=self.user.id,
            llm=llm,
        )

        self.assertEqual(llm.calls, 1)
        self.assertEqual(result.version_no, 2)
        self.assertEqual(result.parent_version_id, self.v1.id)
        self.assertEqual(result.references, self.references)
        self.assertTrue(result.diff_summary)
        self.assertTrue(result.verify_result["passed"])
        self.assertEqual(self.v1.output_json, old_output)
        saved_v2 = self.db.get(BusinessArtifactVersion, result.version_id)
        self.assertEqual(saved_v2.revision_instruction, "把建议措施写得更具体")
        self.assertTrue(saved_v2.diff_summary_json)
        self.assertTrue(saved_v2.verify_result_json["passed"])
        self.assertEqual(
            self.db.query(BusinessArtifactVersion).filter_by(artifact_id=self.run.id).count(),
            2,
        )

        versions = list_artifact_versions(
            self.db,
            artifact_id=self.run.id,
            artifact_type="fmea",
            created_by=self.user.id,
        )
        self.assertEqual(versions.artifact_id, str(self.run.id))
        self.assertEqual(versions.artifact_type, "fmea")
        self.assertEqual(
            [version.version_no for version in versions.versions],
            [1, 2],
        )
        self.assertEqual(versions.versions[1].revision_instruction, "把建议措施写得更具体")
        loaded_v1 = get_artifact_version(
            self.db,
            artifact_id=self.run.id,
            version_id=self.v1.id,
            artifact_type="fmea",
            created_by=self.user.id,
        )
        self.assertEqual(loaded_v1.output_json, old_output)

        artifacts = list_session_artifacts(
            self.db,
            session_id=self.session.id,
            artifact_type="fmea",
            created_by=self.user.id,
        )
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].artifact_id, str(self.run.id))
        self.assertEqual(artifacts[0].latest_version_id, result.version_id)
        self.assertEqual(artifacts[0].latest_version_no, 2)
        self.assertEqual(artifacts[0].updated_at, result.created_at)

    async def test_session_artifacts_are_isolated_and_empty_session_returns_empty(self):
        other_session = ChatSession(
            id="other-revision-session",
            user_id=self.user.id,
            title="empty",
        )
        self.db.add(other_session)
        self.db.commit()

        artifacts = list_session_artifacts(
            self.db,
            session_id=other_session.id,
            artifact_type="fmea",
            created_by=self.user.id,
        )
        self.assertEqual(artifacts, [])

        with self.assertRaises(ArtifactRevisionError) as context:
            list_session_artifacts(
                self.db,
                session_id=self.session.id,
                artifact_type="fmea",
                created_by=self.user.id + 100,
            )
        self.assertEqual(context.exception.code, "artifact_not_found")

    async def test_empty_revision_instruction_does_not_save_version(self):
        with self.assertRaises(ArtifactRevisionError) as context:
            await revise_artifact_version(
                self.db,
                artifact_id=self.run.id,
                artifact_type="fmea",
                base_version_id=self.v1.id,
                revision_instruction="   ",
                created_by=self.user.id,
                llm=FakeLLM([_output("不应执行")]),
            )

        self.assertEqual(context.exception.code, "invalid_revision_instruction")
        self.assertEqual(
            self.db.query(BusinessArtifactVersion).filter_by(artifact_id=self.run.id).count(),
            1,
        )

    async def test_invalid_base_version_does_not_save_version(self):
        with self.assertRaises(ArtifactRevisionError) as context:
            await revise_artifact_version(
                self.db,
                artifact_id=self.run.id,
                artifact_type="fmea",
                base_version_id="missing-version",
                revision_instruction="把建议措施写得更具体",
                created_by=self.user.id,
                llm=FakeLLM([_output("不应执行")]),
            )

        self.assertEqual(context.exception.code, "invalid_base_version")
        self.assertEqual(
            self.db.query(BusinessArtifactVersion).filter_by(artifact_id=self.run.id).count(),
            1,
        )

    async def test_revision_does_not_touch_rag_embedding_or_milvus(self):
        llm = FakeLLM([_output("每班首件和末件检查并测量毛刺高度")])
        rag_module = ModuleType("tools.rag")
        rag_module.retrieve_structured = MagicMock()
        rag_module._get_milvus_client = MagicMock()
        rag_module._emb = SimpleNamespace(embed_query=MagicMock())
        ingest_module = ModuleType("knowledge.ingest")
        ingest_module.ingest_document = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "tools.rag": rag_module,
                "knowledge.ingest": ingest_module,
            },
        ):
            await revise_artifact_version(
                self.db,
                artifact_id=self.run.id,
                artifact_type="fmea",
                base_version_id=self.v1.id,
                revision_instruction="把建议措施写得更具体",
                created_by=self.user.id,
                llm=llm,
            )

        rag_module.retrieve_structured.assert_not_called()
        rag_module._get_milvus_client.assert_not_called()
        rag_module._emb.embed_query.assert_not_called()
        ingest_module.ingest_document.assert_not_called()

    async def test_verifier_repairs_at_most_once(self):
        llm = FakeLLM(
            [
                copy.deepcopy(self.v1.output_json),
                _output("每班首件和末件检查并测量毛刺高度"),
            ]
        )

        result = await revise_artifact_version(
            self.db,
            artifact_id=self.run.id,
            artifact_type="fmea",
            base_version_id=self.v1.id,
            revision_instruction="把建议措施写得更具体",
            created_by=self.user.id,
            llm=llm,
        )

        self.assertEqual(llm.calls, 2)
        self.assertTrue(result.verify_result["repair_attempted"])
        self.assertEqual(result.verify_result["repair_count"], 1)

    async def test_reserved_types_do_not_call_llm(self):
        llm = FakeLLM([_output("不应执行")])
        for artifact_type in ("audit", "report"):
            with self.subTest(artifact_type=artifact_type):
                with self.assertRaises(ArtifactRevisionError) as context:
                    await revise_artifact_version(
                        self.db,
                        artifact_id=self.run.id,
                        artifact_type=artifact_type,
                        base_version_id=self.v1.id,
                        revision_instruction="修改",
                        created_by=self.user.id,
                        llm=llm,
                    )
                self.assertEqual(context.exception.code, "feature_reserved")
        self.assertEqual(llm.calls, 0)

    async def test_invalid_first_json_uses_the_single_repair(self):
        llm = FakeLLM(
            [
                "not-json",
                _output("每班首件和末件检查并测量毛刺高度"),
            ]
        )

        result = await revise_artifact_version(
            self.db,
            artifact_id=self.run.id,
            artifact_type="fmea",
            base_version_id=self.v1.id,
            revision_instruction="把建议措施写得更具体",
            created_by=self.user.id,
            llm=llm,
        )

        self.assertEqual(llm.calls, 2)
        self.assertTrue(result.verify_result["passed"])
        self.assertEqual(result.verify_result["repair_count"], 1)

    async def test_failed_single_repair_does_not_save_version(self):
        unchanged = copy.deepcopy(self.v1.output_json)
        llm = FakeLLM([unchanged, unchanged])

        with self.assertRaises(ArtifactRevisionError) as context:
            await revise_artifact_version(
                self.db,
                artifact_id=self.run.id,
                artifact_type="fmea",
                base_version_id=self.v1.id,
                revision_instruction="把建议措施写得更具体",
                created_by=self.user.id,
                llm=llm,
            )

        self.assertEqual(context.exception.code, "revision_verify_failed")
        self.assertEqual(llm.calls, 2)
        self.assertEqual(
            self.db.query(BusinessArtifactVersion).filter_by(artifact_id=self.run.id).count(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
