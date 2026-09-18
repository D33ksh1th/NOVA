"""
NOVA Runtime Entry

Starts the FastAPI gateway with settings-driven host/port.
"""

import uvicorn

from packages.config import settings


def main() -> None:
    uvicorn.run(
        "services.gateway.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
