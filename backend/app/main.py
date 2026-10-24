from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import AsyncSessionFactory, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "data": exc.detail, "msg": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "data": exc.errors(), "msg": "请求参数校验失败"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    database = "ok"
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    payload: dict[str, Any] = {
        "code": "SUCCESS" if database == "ok" else "SERVICE_UNAVAILABLE",
        "data": {
            "service": "ok",
            "database": database,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "msg": "success" if database == "ok" else "database unavailable",
    }
    return JSONResponse(status_code=200 if database == "ok" else 503, content=payload)
