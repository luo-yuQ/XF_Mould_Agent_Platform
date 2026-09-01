import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "011_create_runtime_core.py"
    )
    fake_op = MagicMock()
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = fake_op
    spec = importlib.util.spec_from_file_location("migration_011_runtime_core", migration_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"alembic": fake_alembic}):
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module, fake_op


def test_runtime_migration_upgrade_creates_only_five_core_tables():
    module, fake_op = _load_migration()
    module.upgrade()

    assert module.revision == "011"
    assert module.down_revision == "010"
    assert [call.args[0] for call in fake_op.create_table.call_args_list] == [
        "runtime_runs",
        "runtime_state_snapshots",
        "runtime_agent_steps",
        "runtime_trace_events",
        "runtime_audit_events",
    ]


def test_runtime_migration_downgrade_drops_only_five_core_tables_in_reverse_order():
    module, fake_op = _load_migration()
    module.downgrade()

    assert [call.args[0] for call in fake_op.drop_table.call_args_list] == [
        "runtime_audit_events",
        "runtime_trace_events",
        "runtime_agent_steps",
        "runtime_state_snapshots",
        "runtime_runs",
    ]
    assert all(
        call.args[0].startswith("runtime_")
        for call in fake_op.drop_table.call_args_list
    )
