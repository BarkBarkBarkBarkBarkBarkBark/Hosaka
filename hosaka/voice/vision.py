"""One-shot vision call used by the `see` tool.

Small, synchronous wrapper around the OpenAI Chat Completions vision
endpoint so a JPEG frame + a prompt turns into a one-paragraph string
the Realtime voice can read aloud.
"""

from __future__ import annotations

import base64
import logging
import os

import httpx

log = logging.getLogger("hosaka.voice.vision")

VISION_MODEL = os.getenv("HOSAKA_VOICE_VISION_MODEL", "gpt-4o-mini")
VISION_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_PROMPT = "Describe what you see in one or two short sentences."


def describe(jpeg: bytes, *, prompt: str = DEFAULT_PROMPT) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return "vision: OPENAI_API_KEY not set"
    if not jpeg:
        return "vision: empty frame"

    b64 = base64.b64encode(jpeg).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "max_tokens": 180,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(VISION_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPError as exc:
        log.warning("vision call failed: %s", exc)
        return f"vision: request failed ({exc})"
    except (KeyError, IndexError, ValueError) as exc:
        return f"vision: unexpected response ({exc})"
