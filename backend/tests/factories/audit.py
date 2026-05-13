"""Factories for audit domain models."""

from __future__ import annotations

import uuid

import factory

from cellar.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    AuthMethod,
    OperationType,
)
from cellar.domain.audit_compliance.models import (
    AuditEntry,
    AuditOperation,
    ElectronicSignature,
)


class AuditEntryFactory(factory.Factory):
    class Meta:
        model = AuditEntry

    id = factory.LazyFunction(uuid.uuid4)
    operation_id = factory.LazyFunction(uuid.uuid4)
    entity_type = "molecule"
    entity_id = factory.LazyFunction(uuid.uuid4)
    field_name = "smiles"
    action = AuditAction.CREATE
    old_value = None
    new_value = "CCO"


class AuditOperationFactory(factory.Factory):
    class Meta:
        model = AuditOperation

    id = factory.LazyFunction(uuid.uuid4)
    workspace_id = factory.LazyFunction(uuid.uuid4)
    operation_type = OperationType.REGISTRATION
    user_id = factory.LazyFunction(uuid.uuid4)
    actor_type = ActorType.USER
    entity_type = "molecule"
    entity_id = factory.LazyFunction(uuid.uuid4)
    status = AuditStatus.COMPLETED


class ElectronicSignatureFactory(factory.Factory):
    class Meta:
        model = ElectronicSignature

    id = factory.LazyFunction(uuid.uuid4)
    operation_id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    meaning = "I approve this assay run"
    auth_method = AuthMethod.PASSWORD
