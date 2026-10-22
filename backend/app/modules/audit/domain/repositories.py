from typing import Protocol
from uuid import UUID
from .entities import AuditEvent

class AuditRepository(Protocol):
    def add(self, event: AuditEvent) -> None: ...
    def list(self, tenant_id: UUID, limit: int, offset: int) -> list[AuditEvent]: ...
