from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from algorithm_video_generator import __version__
from algorithm_video_generator.api.routes import router
from algorithm_video_generator.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Algorithm Video Generator API",
        version=__version__,
        description="Generate narrated algorithm videos from ACM problem materials.",
    )
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "algorithm_video_generator.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
