"""PlayStation-only menu backed by Hosaka's native RetroArch launcher."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hosaka.games import run_play
from hosaka.web.api_v1 import ActionResult, require_auth, require_write

log = logging.getLogger("hosaka.web.games")
router = APIRouter(prefix="/api/v1/games", tags=["games"])


def available() -> None:
    if os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(403, "PlayStation games are disabled on public hosts")


class Game(BaseModel):
    title: str


class GameList(BaseModel):
    games: list[Game]


class LaunchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00-\x1f\x7f]+$")


@router.get("", response_model=GameList, dependencies=[Depends(require_auth), Depends(available)])
def games() -> GameList:
    payload = run_play("list", "psx", wait_s=45)
    if not payload["ok"]:
        raise HTTPException(502, payload.get("error") or "PlayStation catalog failed")
    entries = payload.get("games")
    if not isinstance(entries, list) or any(
        not isinstance(game, dict) or not isinstance(game.get("title"), str) or not game["title"].strip()
        or game.get("system", "psx") != "psx" for game in entries
    ):
        log.error("play list psx returned an invalid PlayStation catalog")
        raise HTTPException(502, "play list psx returned an invalid PlayStation catalog")
    return GameList(games=[Game(title=title) for title in sorted({game["title"] for game in entries}, key=str.casefold)])


@router.post("/launch", response_model=ActionResult, dependencies=[Depends(require_write), Depends(available)])
def launch(body: LaunchRequest) -> ActionResult:
    if body.title not in {game.title for game in games().games}:
        raise HTTPException(404, "Choose a title from the PlayStation catalog")
    if body.title.startswith("-") or body.title.lower() in {"stop", "quit", "exit", "list"}:
        raise HTTPException(422, "This title conflicts with a play command")
    payload = run_play(body.title, wait_s=20)
    if payload.get("action") == "ambiguous":
        raise HTTPException(409, "The launcher found multiple matches; use /play with the exact title")
    if not payload["ok"] or payload.get("action") != "launch":
        raise HTTPException(502, payload.get("error") or payload.get("message") or "Game launch was not confirmed")
    return ActionResult(ok=True, message=f"Launching {body.title} through RetroArch")


@router.post("/stop", response_model=ActionResult, dependencies=[Depends(require_write), Depends(available)])
def stop() -> ActionResult:
    payload = run_play("stop", wait_s=8)
    if not payload["ok"]:
        raise HTTPException(502, payload.get("error") or "Game stop failed")
    return ActionResult(ok=True, message=payload.get("message") or "Game stopped")
