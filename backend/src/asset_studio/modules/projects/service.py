"""Project service: creation, configuration versions, clone, import/export, drafts.

Business rules enforced here: RULE-005 (MCP decisions flag; only the user changes it),
RULE-010 (drafts become projects only by user confirmation), RULE-014 (schema validation),
RULE-006 (every change is audited).
"""

import re
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.config_schema import ProjectConfig, breaking_changes
from asset_studio.modules.projects.models import Project, ProjectConfigVersion, ProjectDraft

EXPORT_FORMAT = "asset-studio-project"


def _require_user(actor: Actor, what: str) -> None:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", f"Only the user can {what}.")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70]
    return slug or "project"


def _unique_slug(session: Session, base: str) -> str:
    slug, n = base, 2
    while session.scalar(select(func.count()).where(Project.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def get_project(session: Session, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise DomainError(404, "PROJECT_NOT_FOUND", "Project not found.")
    return project


def current_config(session: Session, project: Project) -> ProjectConfig:
    row = session.scalar(
        select(ProjectConfigVersion).where(
            ProjectConfigVersion.project_id == project.id,
            ProjectConfigVersion.version == project.current_config_version,
        )
    )
    if row is None:
        raise DomainError(500, "CONFIG_MISSING", "The current configuration version is missing.")
    return ProjectConfig.model_validate(row.config)


def list_projects(session: Session, include_archived: bool = False) -> list[Project]:
    q = select(Project).order_by(Project.name)
    if not include_archived:
        q = q.where(Project.archived_at.is_(None))
    return list(session.scalars(q))


def create_project(
    session: Session, config: ProjectConfig, actor: Actor, *, action: str = "project.created"
) -> Project:
    _require_user(actor, "create a project")  # RULE-010
    project = Project(
        slug=_unique_slug(session, _slugify(config.name)),
        name=config.name,
        type=config.type,
        intended_use=config.intended_use,
        mcp_can_decide=False,  # RULE-005 default
        current_config_version=1,
    )
    session.add(project)
    session.flush()
    session.add(
        ProjectConfigVersion(
            project_id=project.id,
            version=1,
            schema_version=config.schema_version,
            config=config.model_dump(mode="json"),
            created_by_actor=actor,
        )
    )
    record(
        session,
        actor=actor,
        action=action,
        subject_type="project",
        subject_id=project.id,
        project_id=project.id,
        data={"slug": project.slug},
    )
    return project


def update_config(
    session: Session,
    project_id: uuid.UUID,
    config: ProjectConfig,
    actor: Actor,
    *,
    acknowledge_breaking: bool = False,
    note: str = "",
) -> tuple[Project, list[str]]:
    _require_user(actor, "change the project configuration")
    project = get_project(session, project_id)
    old = current_config(session, project)
    changes = breaking_changes(old, config)
    if changes and not acknowledge_breaking:
        raise DomainError(
            409,
            "CONFIG_BREAKING_CHANGE",
            "The change can affect existing assets or exports. Confirm to continue.",
            {"changes": changes},
        )
    project.current_config_version += 1
    project.name, project.type, project.intended_use = config.name, config.type, config.intended_use
    session.add(
        ProjectConfigVersion(
            project_id=project.id,
            version=project.current_config_version,
            schema_version=config.schema_version,
            config=config.model_dump(mode="json"),
            created_by_actor=actor,
            note=note[:500],
        )
    )
    record(
        session,
        actor=actor,
        action="project.config_updated",
        subject_type="project",
        subject_id=project.id,
        project_id=project.id,
        data={"version": project.current_config_version, "breaking": changes},
    )
    return project, changes


def set_mcp_can_decide(
    session: Session, project_id: uuid.UUID, value: bool, actor: Actor
) -> Project:
    _require_user(actor, "change whether Claude may approve and publish")  # RULE-005
    project = get_project(session, project_id)
    if project.mcp_can_decide != value:
        project.mcp_can_decide = value
        record(
            session,
            actor=actor,
            action="project.mcp_can_decide_changed",
            subject_type="project",
            subject_id=project.id,
            project_id=project.id,
            data={"value": value},
        )
    return project


def set_archived(session: Session, project_id: uuid.UUID, archived: bool, actor: Actor) -> Project:
    _require_user(actor, "archive or restore a project")
    project = get_project(session, project_id)
    if (project.archived_at is not None) != archived:
        project.archived_at = utcnow() if archived else None
        record(
            session,
            actor=actor,
            action="project.archived" if archived else "project.restored",
            subject_type="project",
            subject_id=project.id,
            project_id=project.id,
        )
    return project


def clone_project(session: Session, project_id: uuid.UUID, name: str, actor: Actor) -> Project:
    source = get_project(session, project_id)
    config = current_config(session, source).model_copy(update={"name": name})
    project = create_project(session, config, actor, action="project.cloned")
    record(
        session,
        actor=actor,
        action="project.cloned_from",
        subject_type="project",
        subject_id=project.id,
        project_id=project.id,
        data={"source_id": str(source.id)},
    )
    return project


def config_versions(session: Session, project_id: uuid.UUID) -> list[ProjectConfigVersion]:
    get_project(session, project_id)
    q = (
        select(ProjectConfigVersion)
        .where(ProjectConfigVersion.project_id == project_id)
        .order_by(ProjectConfigVersion.version.desc())
    )
    return list(session.scalars(q))


def export_document(session: Session, project_id: uuid.UUID) -> dict[str, Any]:
    project = get_project(session, project_id)
    return {
        "format": EXPORT_FORMAT,
        "format_version": 1,
        "config": current_config(session, project).model_dump(mode="json"),
    }


def _validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]


def import_document(session: Session, document: dict[str, Any], actor: Actor) -> Project:
    if document.get("format") != EXPORT_FORMAT or document.get("format_version") != 1:
        raise DomainError(
            422, "IMPORT_FORMAT_UNSUPPORTED", "This file is not an Asset Studio project export."
        )
    try:
        config = ProjectConfig.model_validate(document.get("config"))
    except ValidationError as exc:
        raise DomainError(
            422,
            "CONFIG_INVALID",
            "The configuration is not valid.",
            {"errors": _validation_details(exc)},
        ) from exc
    return create_project(session, config, actor, action="project.imported")


def create_draft(
    session: Session,
    *,
    description: str,
    config: dict[str, Any],
    assumptions: list[str],
    missing: list[str],
    actor: Actor,
) -> tuple[ProjectDraft, list[dict[str, Any]]]:
    draft = ProjectDraft(
        description=description[:4000],
        config=config,
        assumptions=assumptions[:50],
        missing=missing[:50],
        created_by_actor=actor,
    )
    session.add(draft)
    session.flush()
    record(
        session,
        actor=actor,
        action="project_draft.created",
        subject_type="project_draft",
        subject_id=draft.id,
    )
    return draft, draft_problems(draft)


def draft_problems(draft: ProjectDraft) -> list[dict[str, Any]]:
    try:
        ProjectConfig.model_validate(draft.config)
    except ValidationError as exc:
        return _validation_details(exc)
    return []


def get_draft(session: Session, draft_id: uuid.UUID) -> ProjectDraft:
    draft = session.get(ProjectDraft, draft_id)
    if draft is None:
        raise DomainError(404, "DRAFT_NOT_FOUND", "Draft not found.")
    return draft


def confirm_draft(
    session: Session, draft_id: uuid.UUID, config: ProjectConfig, actor: Actor
) -> Project:
    _require_user(actor, "confirm a project draft")  # RULE-010
    draft = get_draft(session, draft_id)
    if draft.status != "pending":
        raise DomainError(409, "DRAFT_NOT_PENDING", "This draft was already handled.")
    project = create_project(session, config, actor)
    draft.status, draft.project_id = "confirmed", project.id
    record(
        session,
        actor=actor,
        action="project_draft.confirmed",
        subject_type="project_draft",
        subject_id=draft.id,
        project_id=project.id,
    )
    return project
