"""Standalone reference actions. Context is supplied explicitly by the caller."""
from __future__ import annotations

from typing import Protocol


class Context(Protocol):
    def read_data(self, name: str) -> str | None: ...
    def write_data(self, name: str, value: str) -> None: ...
    def delete_data(self, name: str) -> None: ...
    def log(self, event: str, metadata: dict) -> None: ...


def run(action: str, params: dict, context: Context) -> dict:
    if action not in {"echo", "save", "load", "delete", "fail"}:
        raise ValueError("Unknown reference action.")
    if action in {"echo", "save"}:
        if set(params) != {"message"} or not isinstance(params["message"], str) or len(params["message"]) > 2048:
            raise ValueError("Provide only message, a string of at most 2048 characters.")
    elif params:
        raise ValueError("This action does not accept parameters.")
    message = ""
    error = None
    if action == "echo":
        message = params["message"]
    elif action == "save":
        context.write_data("example.txt", params["message"])
        message = "Saved example value."
    elif action == "load":
        message = context.read_data("example.txt") or ""
    elif action == "delete":
        context.delete_data("example.txt")
        message = "Deleted example value."
    else:
        error = "Intentional reference error."
    context.log("reference.action", {"action": action, "success": error is None})
    return {
        "success": error is None, "message": message, "error": error,
        "rows": [{"name": "action", "value": action}],
    }
