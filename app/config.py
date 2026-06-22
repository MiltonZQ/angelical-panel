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

CAL_API_KEY = os.getenv("CAL_API_KEY", "cal_live_05087d22a1b45b6491878a31ae936af2")
CAL_USERNAME = os.getenv("CAL_USERNAME", "fundacionangelical-kwdgm7")
CAL_EVENT_SLUG = os.getenv("CAL_EVENT_SLUG", "consulta")
CAL_API_VERSION_SLOTS = os.getenv("CAL_API_VERSION_SLOTS", "2024-09-04")
CAL_API_VERSION_BOOKINGS = os.getenv("CAL_API_VERSION_BOOKINGS", "2024-08-13")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "America/Bogota")
