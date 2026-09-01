"""Deterministic no-side-effect capability for the Core vertical slice."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from runtime.capabilities.core import CapabilityDefinition, CapabilityRegistry
from runtime.tenant_context import TenantContext


DEMO_CAPABILITY_NAME = "demo.echo"


class DemoEchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=1000)


def _demo_echo(_context: TenantContext, arguments: dict[str, object]) -> dict[str, object]:
    return {"echo": arguments["value"]}


def register_demo_capability(registry: CapabilityRegistry) -> None:
    registry.register(
        CapabilityDefinition(
            name=DEMO_CAPABILITY_NAME,
            input_schema=DemoEchoInput,
            handler=_demo_echo,
        )
    )
