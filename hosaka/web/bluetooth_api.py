"""Small BlueZ surface for the local cyberdeck menu."""
from __future__ import annotations

import os
import re
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hosaka.web.api_v1 import ActionResult, _run, require_auth, require_write

router = APIRouter(prefix="/api/v1/bluetooth", tags=["bluetooth"])


def available() -> None:
    if os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(403, "Bluetooth is disabled on public hosts")
    if not shutil.which("bluetoothctl"):
        raise HTTPException(501, "Bluetooth pairing requires BlueZ on the cyberdeck; use system Bluetooth settings on this host")


def command(*args: str, timeout: int = 12) -> str:
    rc, out, err = _run(["bluetoothctl", *args], timeout=timeout)
    if rc != 0 or re.search(r"\b(Failed|Error|not available|not ready)\b", out + err, re.I):
        raise HTTPException(502, (err or out).strip()[:400] or "Bluetooth command failed")
    return out


class PairRequest(BaseModel):
    address: str = Field(pattern=r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class BluetoothDevice(BaseModel):
    address: str
    name: str


class BluetoothList(BaseModel):
    devices: list[BluetoothDevice]


@router.get("/devices", response_model=BluetoothList, dependencies=[Depends(require_auth), Depends(available)])
def devices() -> BluetoothList:
    out = command("devices")
    result = []
    for line in out.splitlines():
        match = re.match(r"Device ((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.+)", line)
        if match:
            result.append(BluetoothDevice(address=match[1], name=match[2]))
    return BluetoothList(devices=result)


@router.post("/scan", response_model=BluetoothList, dependencies=[Depends(require_write), Depends(available)])
def scan() -> BluetoothList:
    command("power", "on")
    command("--timeout", "8", "scan", "on", timeout=12)
    return devices()


@router.post("/pair", response_model=ActionResult, dependencies=[Depends(require_write), Depends(available)])
def pair(body: PairRequest) -> ActionResult:
    info = command("info", body.address)
    if not re.search(r"Paired:\s+yes", info):
        command("--agent", "NoInputNoOutput", "--timeout", "30", "pair", body.address, timeout=35)
        if not re.search(r"Paired:\s+yes", command("info", body.address)):
            raise HTTPException(502, "Pairing did not complete; use system Bluetooth settings if a PIN or passkey is required")
    command("trust", body.address)
    command("--timeout", "15", "connect", body.address, timeout=20)
    if not re.search(r"Connected:\s+yes", command("info", body.address)):
        raise HTTPException(502, "Device paired but connection did not complete")
    return ActionResult(ok=True, message=f"Connected to {body.address}")
