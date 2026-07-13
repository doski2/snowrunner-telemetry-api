"""CLI: uvicorn snowrunner_telemetry_api.main:app"""

from __future__ import annotations

import uvicorn

from .config import DEFAULT_HOST, api_port


def main() -> None:
    uvicorn.run(
        "snowrunner_telemetry_api.main:app",
        host=DEFAULT_HOST,
        port=api_port(),
        reload=False,
    )


if __name__ == "__main__":
    main()
