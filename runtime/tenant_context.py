"""Shared tenant-boundary validation for Runtime entry points."""

from __future__ import annotations

from dataclasses import dataclass


class TenantBoundaryError(PermissionError):
    """Raised before a Runtime operation crosses or omits a tenant boundary."""


def _normalize_tenant_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TenantBoundaryError("tenant_id is required")
    normalized = value.strip()
    if len(normalized) > 128:
        raise TenantBoundaryError("tenant_id exceeds the maximum length")
    return normalized


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Authoritative tenant identity supplied by auth or a trusted worker envelope."""

    tenant_id: str
    principal_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _normalize_tenant_id(self.tenant_id))
        if self.principal_id is not None and (
            not isinstance(self.principal_id, str) or not self.principal_id.strip()
        ):
            raise TenantBoundaryError("principal_id cannot be empty")


def require_tenant_context(context: TenantContext | None) -> TenantContext:
    """Reject missing or malformed trusted context before dispatch."""

    if context is None:
        raise TenantBoundaryError("tenant context is required")
    if not isinstance(context, TenantContext):
        raise TenantBoundaryError("invalid tenant context")
    return context


def ensure_same_tenant(
    context: TenantContext | None,
    resource_tenant_id: object,
) -> None:
    """Ensure a resource belongs to the tenant making the request."""

    trusted_context = require_tenant_context(context)
    resource_tenant = _normalize_tenant_id(resource_tenant_id)
    if trusted_context.tenant_id != resource_tenant:
        raise TenantBoundaryError("tenant boundary mismatch")
