"""Workflow templates: an engine graph plus the inputs it declares (ADR-006).

The domain fills named inputs ("prompt", "seed", ...). Only the template knows which engine
node and field each input lands in, so engine node ids never leak into the domain.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Literal

from asset_studio.errors import DomainError

InputType = Literal["string", "integer", "number", "boolean"]

_PY_TYPES: dict[InputType, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


@dataclass(frozen=True)
class InputSpec:
    """Where an input goes: ``targets`` are (node id, field) pairs in the graph."""

    type: InputType
    targets: tuple[tuple[str, str], ...]
    required: bool = True
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    version: int
    graph: dict[str, Any]
    inputs: dict[str, InputSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, spec in self.inputs.items():
            for node, key in spec.targets:
                if key not in self.graph.get(node, {}).get("inputs", {}):
                    raise ValueError(f"Input {name!r} targets missing {node}.{key}")

    def render(self, values: dict[str, Any]) -> dict[str, Any]:
        """A copy of the graph with the values written in. Rejects unknown, missing and
        out-of-range values with WORKFLOW_INPUT_INVALID."""
        unknown = sorted(set(values) - set(self.inputs))
        if unknown:
            raise _invalid(f"Unknown inputs: {', '.join(unknown)}.", unknown)
        graph = copy.deepcopy(self.graph)
        for name, spec in self.inputs.items():
            value = values.get(name, spec.default)
            if value is None:
                if spec.required:
                    raise _invalid(f"Input {name!r} is required.", [name])
                continue
            _check(name, spec, value)
            for node, key in spec.targets:
                graph[node]["inputs"][key] = value
        return graph


def _check(name: str, spec: InputSpec, value: Any) -> None:
    ok = isinstance(value, _PY_TYPES[spec.type])
    if spec.type in ("integer", "number") and isinstance(value, bool):
        ok = False
    if not ok:
        raise _invalid(f"Input {name!r} must be a {spec.type}.", [name])
    if spec.minimum is not None and value < spec.minimum:
        raise _invalid(f"Input {name!r} must be at least {spec.minimum}.", [name])
    if spec.maximum is not None and value > spec.maximum:
        raise _invalid(f"Input {name!r} must be at most {spec.maximum}.", [name])


def _invalid(detail: str, inputs: list[str]) -> DomainError:
    return DomainError(422, "WORKFLOW_INPUT_INVALID", detail, {"inputs": inputs})
