"""4.6 业务产物追改 MVP 最小验收用例。"""
from __future__ import annotations

from tests.test_artifact_revision_service import ArtifactRevisionServiceTests


class ArtifactRevisionMvpCases(ArtifactRevisionServiceTests):
    async def test_case_001_fmea_revise_action(self):
        await self.test_revision_creates_new_version_and_preserves_base()

    async def test_case_002_empty_revision_instruction(self):
        await self.test_empty_revision_instruction_does_not_save_version()

    async def test_case_003_reserved_audit_report(self):
        await self.test_reserved_types_do_not_call_llm()

    async def test_case_004_no_milvus_write(self):
        await self.test_revision_does_not_touch_rag_embedding_or_milvus()

    async def test_case_005_existing_fmea_flow_still_works(self):
        self.assertEqual(self.v1.version_no, 1)
        self.assertEqual(self.v1.operation_type, "create")
        self.assertIsNone(self.v1.parent_version_id)
