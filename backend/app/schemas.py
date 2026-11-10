"""Pydantic models for the shared contract (request bodies + the IR / report shapes for docs and validation)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NodeType = Literal["page", "container", "card", "form", "header", "navbar", "nav_item", "heading", "text", "link",
                   "button", "input", "textarea", "checkbox", "radio", "select", "image", "list", "divider", "icon"]


class Open(BaseModel):
    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- IR

class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Action(Open):
    type: Literal["validate_required", "validate_format", "show_message", "navigate", "toggle_visibility", "set_text"]


class Event(Open):
    on: Literal["click", "submit", "change"] = "click"
    actions: list[Action] = []


class Relation(Open):
    type: Literal["below", "above", "left_of", "right_of", "inside", "label_for"]
    target: str


class Node(Open):
    id: str
    type: NodeType
    label: str = ""
    props: dict[str, Any] = {}
    style: dict[str, Any] = {}
    layout: dict[str, Any] | None = None
    bbox: BBox | None = None
    children: list["Node"] | None = None
    relations: list[Relation] = []
    events: list[Event] = []
    origin: Literal["sketch", "voice", "repair", "manual"] = "manual"


class Page(Open):
    id: str
    name: str
    route: str = "/"
    root: Node


class IR(Open):
    schema_: str = Field("neurogenui.ir/1", alias="schema")
    meta: dict[str, Any] = {}
    pages: list[Page]
    next_id: int = 1


# --------------------------------------------------------------------------- Ops

class Op(Open):
    op: Literal["add", "remove", "modify", "move", "resize", "style", "interaction", "navigation", "create"]
    target: dict[str, Any] | None = None
    component: dict[str, Any] | None = None
    components: list[dict[str, Any]] | None = None
    position: dict[str, Any] | None = None
    changes: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    page: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    scale: float | None = None
    confidence: float | None = None


# --------------------------------------------------------------------------- request bodies

class ProjectCreate(BaseModel):
    name: str = "Untitled project"


class AnalyzeRequest(BaseModel):
    sketch_id: str
    mode: Literal["cv", "vision", "hybrid"] = "hybrid"


class InterpretRequest(BaseModel):
    text: str
    project_id: str | None = None
    version: int | None = None


class GenerateRequest(BaseModel):
    project_id: str | None = None
    sketch_id: str | None = None
    text: str = ""
    source: Literal["voice", "text"] = "text"
    mode: Literal["cv", "vision", "hybrid"] = "hybrid"
    auto_repair: bool = True
    transcribe_ms: int | None = None


class ModifyRequest(BaseModel):
    project_id: str
    text: str = ""
    source: Literal["voice", "text"] = "text"
    base_version: int | None = None
    auto_repair: bool = True
    transcribe_ms: int | None = None
    ops: list[Op] | None = None


class ValidateRequest(BaseModel):
    project_id: str
    version: int | None = None
    repair: bool = False


class IRPatch(BaseModel):
    ir: dict[str, Any]
    base_version: int | None = None


class CodePut(BaseModel):
    files: dict[str, str] = {}
    preview: str
    base_version: int | None = None


class Check(Open):
    id: str
    kind: Literal["visual", "functional"]
    name: str
    ok: bool
    detail: str = ""
    target: str | None = None


class ValidationReport(Open):
    passed: bool
    score: float
    checks: list[Check]
    visual: dict[str, float]
    functional: dict[str, Any]
    dom: list[dict[str, Any]] = []
    duration_ms: int = 0
