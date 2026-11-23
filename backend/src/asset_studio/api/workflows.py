"""Workflows (brief 6.9): the built-in, versioned ComfyUI templates. Generation picks one
from the request's inputs (D-53); importing workflows comes later."""

from fastapi import APIRouter
from pydantic import BaseModel

from asset_studio.api.security import CurrentActor
from asset_studio.modules.workflows.builtin import ALL, remove_background, template

router = APIRouter()


class WorkflowOut(BaseModel):
    id: str
    version: int
    engine: str
    builtin: bool
    inputs: list[str]


@router.get("", response_model=list[WorkflowOut])
def list_workflows(_: CurrentActor) -> list[WorkflowOut]:
    templates = [template(f) for f in ALL] + [remove_background()]
    return [
        WorkflowOut(
            id=t.id, version=t.version, engine="comfyui", builtin=True, inputs=sorted(t.inputs)
        )
        for t in templates
    ]
