import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.db import close_pool, get_pool
from app.admin import admin_router

logger = logging.getLogger("uvicorn.error")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await get_pool()
        logger.info("Database pool created successfully")
    except Exception as e:
        logger.error(f"Database pool creation failed: {e}")
    yield
    await close_pool()


app = FastAPI(title="Panel Casa Angelical", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="angelical_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=True,
)

app.include_router(admin_router)


@app.get("/health")
async def health():
    return "ok"
