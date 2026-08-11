import os
from urllib.parse import quote_plus


ADMIN_USER = os.getenv("ADMIN_USER", "CasaAngelical")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Angelical.5768!")
SESSION_SECRET = os.getenv("SESSION_SECRET", "angelical-panel-2026-change-me")

DB_HOST = os.getenv("DB_HOST", "aws-1-us-east-1.pooler.supabase.com")
DB_PORT = os.getenv("DB_PORT", "6543")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres.nmxrtgwshqapberjalnb")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Fundacion.2626!")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

CAL_API_KEY = os.getenv("CAL_API_KEY", "cal_live_0fb4c215f68004580b341a40ee4b7949")
CAL_USERNAME = os.getenv("CAL_USERNAME", "ivan-rodriguez-4d2xaw")
CAL_EVENT_SLUG = os.getenv("CAL_EVENT_SLUG", "consulta")
CAL_EVENT_TYPE_ID = int(os.getenv("CAL_EVENT_TYPE_ID", "5887685"))
CAL_API_VERSION_SLOTS = os.getenv("CAL_API_VERSION_SLOTS", "2024-09-04")
CAL_API_VERSION_BOOKINGS = os.getenv("CAL_API_VERSION_BOOKINGS", "2024-08-13")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "America/Bogota")

# ── Reglas de agendamiento de primera consulta ──────────────
# Se aplican en código (app/cal.py). El modelo del bot NO puede saltárselas.
CAL_MAX_CITAS_DIA = int(os.getenv("CAL_MAX_CITAS_DIA", "4"))
CAL_PRIMER_SLOT = os.getenv("CAL_PRIMER_SLOT", "09:00")
CAL_ULTIMO_SLOT = os.getenv("CAL_ULTIMO_SLOT", "11:00")
CAL_HORIZONTE_DIAS = int(os.getenv("CAL_HORIZONTE_DIAS", "60"))
CAL_MAX_DIAS_MOSTRAR = int(os.getenv("CAL_MAX_DIAS_MOSTRAR", "2"))
CAL_MAX_HORAS_MOSTRAR = int(os.getenv("CAL_MAX_HORAS_MOSTRAR", "5"))
