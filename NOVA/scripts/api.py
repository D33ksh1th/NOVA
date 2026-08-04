import uvicorn

from packages.config import settings


def main():
    uvicorn.run(
        "services.gateway.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()