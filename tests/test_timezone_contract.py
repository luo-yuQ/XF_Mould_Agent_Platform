import unittest
from datetime import timezone

from models.audit import AuditRun
from models.chat import ChatMessage, ChatSession, ChatSessionSummary
from models.fmea import FMEARun
from models.report import ReportRun
from models.user import User
from time_utils import utc_now


class TimezoneContractTests(unittest.TestCase):
    def test_utc_now_returns_aware_utc_datetime(self):
        value = utc_now()

        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.utcoffset(), timezone.utc.utcoffset(value))

    def test_persisted_timestamp_columns_are_timezone_aware(self):
        timestamp_columns = (
            User.created_at,
            User.updated_at,
            ChatSession.created_at,
            ChatSession.updated_at,
            ChatMessage.created_at,
            ChatSessionSummary.updated_at,
            FMEARun.created_at,
            FMEARun.updated_at,
            AuditRun.created_at,
            AuditRun.updated_at,
            ReportRun.created_at,
            ReportRun.updated_at,
        )

        for column in timestamp_columns:
            with self.subTest(column=str(column)):
                self.assertTrue(column.property.columns[0].type.timezone)


if __name__ == "__main__":
    unittest.main()
