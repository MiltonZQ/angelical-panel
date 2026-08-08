import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.db import close_pool, get_pool, get_control_slots, insert_control, is_valid_appointment_date, invalid_date_error
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


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/login", status_code=302)


@app.get("/health")
async def health():
    return "ok"


@app.get("/favicon.ico")
async def favicon():
    return ""


@app.get("/api/validar-fecha")
async def api_validar_fecha(fecha: str = ""):
    if not fecha:
        return JSONResponse({"valida": False, "motivo": "Falta parámetro fecha (YYYY-MM-DD)"})
    if is_valid_appointment_date(fecha):
        return JSONResponse({"fecha": fecha, "valida": True, "motivo": "Día hábil de atención"})
    return JSONResponse({"fecha": fecha, "valida": False, "motivo": invalid_date_error(fecha)})


@app.get("/api/control-slots")
async def api_control_slots(fecha: str = ""):
    try:
        pool = await get_pool()
        if not fecha:
            return JSONResponse({"slots": [], "error": "Falta parámetro fecha (YYYY-MM-DD)"})
        if not is_valid_appointment_date(fecha):
            return JSONResponse({"slots": [], "error": invalid_date_error(fecha)})
        horas = await get_control_slots(pool, fecha)
        return JSONResponse({"slots": horas})
    except Exception as e:
        logger.error(f"control-slots error: {e}")
        return JSONResponse({"slots": [], "error": str(e)})


@app.post("/api/control-agendar")
async def api_control_agendar(request: Request):
    try:
        data = await request.json()
        fecha = data.get("fecha", "")
        if not fecha:
            return JSONResponse({"ok": False, "error": "Falta fecha (YYYY-MM-DD)"})
        if not is_valid_appointment_date(fecha):
            return JSONResponse({"ok": False, "error": invalid_date_error(fecha)})
        hora = data.get("hora", "")
        if not hora:
            return JSONResponse({"ok": False, "error": "Falta hora (HH:MM)"})
        nombre = data.get("nombre", "")
        if not nombre:
            return JSONResponse({"ok": False, "error": "Falta nombre del paciente"})
        pool = await get_pool()
        row = await insert_control(
            pool,
            nombre=nombre,
            telefono=data.get("telefono", ""),
            email=data.get("email", ""),
            fecha=fecha,
            hora=hora,
            motivo=data.get("motivo", ""),
        )
        return JSONResponse({"ok": True, "id": row["id"]})
    except Exception as e:
        logger.error(f"control-agendar error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})
