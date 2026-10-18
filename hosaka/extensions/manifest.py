"""Strict, non-executing validation of extension packages and declarative views."""
from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_DOCUMENT_BYTES = 262144
ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
RESERVED = {"core", "hosaka", "settings", "network", "update", "secrets", "shell", "extensions", "safe-mode"}


class ExtensionError(ValueError):
    pass


def validate_id(value: str) -> str:
    if not re.fullmatch(ID_PATTERN, value) or len(value) > 64 or value in RESERVED:
        raise ExtensionError("Use a non-reserved lowercase kebab-case extension ID (maximum 64 characters).")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Requires(StrictModel):
    hosaka_api: Literal[1]

    @field_validator("hosaka_api", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("API version must be an integer")
        return value


class Entrypoint(StrictModel):
    file: str = Field(min_length=1, max_length=200)
    callable: str = Field(pattern=r"^[A-Za-z_][A-Za-z_0-9]*$", max_length=64)


class UI(StrictModel):
    mode: Literal["declarative"]
    file: str = Field(min_length=1, max_length=200)


class Permissions(StrictModel):
    network: Literal[False]
    filesystem: Literal["data-only", "none"]
    subprocess: Literal[False]

    @field_validator("network", "subprocess", mode="before")
    @classmethod
    def boolean_permission(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Permission must be a boolean")
        return value


class Menu(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    icon: Literal["puzzle", "file", "tool", "book"] = "puzzle"
    order: int = Field(default=100, ge=0, le=10000)


class Action(StrictModel):
    description: str = Field(min_length=1, max_length=300)
    input_schema: str = Field(min_length=1, max_length=200)
    output_schema: str = Field(min_length=1, max_length=200)


class Limits(StrictModel):
    timeout_seconds: int = Field(ge=1, le=60)
    max_output_bytes: int = Field(ge=1024, le=1048576)


class Manifest(StrictModel):
    schema_version: Literal[1]
    id: str
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    description: str = Field(min_length=1, max_length=500)
    requires: Requires
    type: Literal["view"]
    category: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    entrypoint: Entrypoint
    ui: UI
    permissions: Permissions
    menu: Menu
    actions: dict[str, Action] = Field(min_length=1, max_length=32)
    limits: Limits

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value

    @field_validator("id")
    @classmethod
    def extension_id(cls, value: str) -> str:
        return validate_id(value)

    @field_validator("actions")
    @classmethod
    def action_ids(cls, values: dict[str, Action]) -> dict[str, Action]:
        for name in values:
            validate_id(name)
        return values


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate YAML fields instead of taking the last value."""


def _mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ExtensionError("YAML fields must be unique string keys.")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def package_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ExtensionError("Package references must be relative files without '..' or backslashes.")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ExtensionError(f"Package file is missing or escapes the package: {relative!r}")
    return target


def read_document(path: Path, *, json_only: bool = False) -> Any:
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ExtensionError(f"Expected a regular document file: {path.name}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ExtensionError(f"Document exceeds {MAX_DOCUMENT_BYTES} bytes: {path.name}")
        text = raw.decode("utf-8")
        def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ExtensionError("JSON fields must be unique.")
                result[key] = value
            return result

        return json.loads(text, object_pairs_hook=unique_pairs) if json_only else yaml.load(text, Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError, RecursionError) as exc:
        raise ExtensionError(f"Cannot read valid {'JSON' if json_only else 'YAML'}: {path.name}") from exc


def validate_schema(document: object) -> None:
    if not isinstance(document, dict):
        raise ExtensionError("Action schemas must be JSON Schema objects.")
    count = 0
    references: list[str] = []

    def visit(value: object, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if count > 4096 or depth > 32:
            raise ExtensionError("Action schema is too complex.")
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$id", "$dynamicRef", "$recursiveRef"}:
                    raise ExtensionError(f"Schema keyword {key} is unsupported.")
                if key == "$ref" and (not isinstance(item, str) or not (item == "#" or item.startswith("#/"))):
                    raise ExtensionError("Only local JSON Schema fragment references are supported.")
                if key == "$ref" and isinstance(item, str):
                    references.append(item)
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)

    visit(document)
    for reference in references:
        target: Any = document
        try:
            for part in reference[2:].split("/") if reference != "#" else []:
                key = part.replace("~1", "/").replace("~0", "~")
                target = target[int(key)] if isinstance(target, list) else target[key]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ExtensionError("JSON Schema fragment reference does not exist.") from exc
        if not isinstance(target, (dict, bool)):
            raise ExtensionError("JSON Schema reference must point to a schema.")
    if document.get("$schema", "https://json-schema.org/draft/2020-12/schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ExtensionError("Only JSON Schema draft 2020-12 is supported.")
    try:
        Draft202012Validator.check_schema(document)
    except SchemaError as exc:
        raise ExtensionError("Invalid action JSON Schema.") from exc


UI_FIELDS = {
    "Stack": {"type", "children"},
    "Heading": {"type", "text"},
    "Text": {"type", "text"},
    "Button": {"type", "label", "action", "params"},
    "TextInput": {"type", "id", "label", "default"},
    "NumberInput": {"type", "id", "label", "default"},
    "Select": {"type", "id", "label", "options", "default"},
    "Checkbox": {"type", "id", "label", "default"},
    "Result": {"type", "bind"},
    "Error": {"type", "bind"},
    "Status": {"type", "bind"},
    "Table": {"type", "bind", "columns"},
}


def validate_view(document: object, actions: set[str]) -> None:
    if not isinstance(document, dict) or set(document) != {"version", "view"}:
        raise ExtensionError("UI must contain only version and view.")
    if type(document["version"]) is not int or document["version"] != 1:
        raise ExtensionError("Unsupported UI version.")
    ids: set[str] = set()
    bindings: list[str] = []
    count = 0

    def visit(component: object, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if count > 128 or depth > 12:
            raise ExtensionError("UI exceeds 128 components or 12 nesting levels.")
        if not isinstance(component, dict) or not isinstance(component.get("type"), str):
            raise ExtensionError("Every UI component must have a type.")
        kind = component["type"]
        if kind not in UI_FIELDS or set(component) - UI_FIELDS[kind]:
            raise ExtensionError("Unknown UI component or unsupported field.")
        for field in ("text", "label"):
            if field in UI_FIELDS[kind]:
                value = component.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 2048:
                    raise ExtensionError(f"{kind} requires bounded nonempty {field}.")
        if "id" in UI_FIELDS[kind]:
            identifier = component.get("id")
            if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identifier) or identifier in ids:
                raise ExtensionError("UI input IDs must be unique lowercase identifiers.")
            ids.add(identifier)
        if kind == "Stack":
            children = component.get("children")
            if not isinstance(children, list) or not children:
                raise ExtensionError("Stack requires nonempty children.")
            for child in children:
                visit(child, depth + 1)
        if kind == "Button":
            action = component.get("action")
            if not isinstance(action, str) or action not in actions:
                raise ExtensionError("UI button refers to an undeclared action.")
            if "params" in component:
                parameters = component["params"]
                if not isinstance(parameters, dict) or len(parameters) > 32:
                    raise ExtensionError("Button params must map bounded property names to input bindings.")
                for name, binding in parameters.items():
                    if (
                        not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
                        or not isinstance(binding, str) or not re.fullmatch(r"params\.[a-z][a-z0-9_]{0,63}", binding)
                    ):
                        raise ExtensionError("Button params use only params.<input_id> bindings.")
                    bindings.append(binding)
        if kind == "Select":
            options = component.get("options")
            if not isinstance(options, list) or not 1 <= len(options) <= 100 or any(
                not isinstance(option, str) or not option or len(option) > 200 for option in options
            ) or len(set(options)) != len(options):
                raise ExtensionError("Select requires unique bounded string options.")
            if "default" in component and component["default"] not in options:
                raise ExtensionError("Select default must be one of its options.")
        if "default" in component:
            value = component["default"]
            valid = {
                "TextInput": isinstance(value, str) and len(value) <= 2048,
                "NumberInput": isinstance(value, (int, float)) and not isinstance(value, bool) and -1e12 <= value <= 1e12,
                "Checkbox": type(value) is bool,
                "Select": True,
            }.get(kind, False)
            if not valid:
                raise ExtensionError("Invalid UI input default.")
        if "bind" in UI_FIELDS[kind]:
            binding = component.get("bind")
            if not isinstance(binding, str) or not re.fullmatch(r"(params|result)\.[a-z][a-z0-9_]{0,63}", binding):
                raise ExtensionError("Bindings must be params.<input_id> or result.<field>.")
            bindings.append(binding)
        if kind == "Table":
            columns = component.get("columns")
            if not isinstance(columns, list) or not 1 <= len(columns) <= 16 or any(
                not isinstance(column, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", column) for column in columns
            ):
                raise ExtensionError("Table requires bounded column identifiers.")

    visit(document["view"])
    if any(binding.startswith("params.") and binding[7:] not in ids for binding in bindings):
        raise ExtensionError("UI binding refers to an unknown input.")


@dataclass(frozen=True)
class Package:
    root: Path
    manifest: Manifest
    view: dict[str, Any]


def validate_package(root: Path) -> Package:
    root = root.expanduser().resolve()
    try:
        manifest = Manifest.model_validate(read_document(package_file(root, "extension.yaml")))
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        raise ExtensionError(f"Invalid extension manifest fields: {fields}") from exc
    entrypoint = package_file(root, manifest.entrypoint.file)
    if entrypoint.suffix != ".py":
        raise ExtensionError("The initial extension API supports Python entrypoint files only.")
    for action in manifest.actions.values():
        for name in (action.input_schema, action.output_schema):
            validate_schema(read_document(package_file(root, name), json_only=True))
    view = read_document(package_file(root, manifest.ui.file))
    validate_view(view, set(manifest.actions))
    return Package(root, manifest, view)
