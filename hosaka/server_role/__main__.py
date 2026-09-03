from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "hosaka.server_role.app:app",
        host=os.getenv("HOSAKA_INFERENCE_HOST", "0.0.0.0"),
        port=int(os.getenv("HOSAKA_INFERENCE_PORT", "8421")),
    )


if __name__ == "__main__":
    main()