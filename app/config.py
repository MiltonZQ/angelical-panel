import os


ADMIN_USER = os.getenv("ADMIN_USER", "CasaAngelical")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Angelical.5768!")
SESSION_SECRET = os.getenv("SESSION_SECRET", "angelical-panel-session-secret-change-in-production-2026")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.nmxrtgwshqapberjalnb:Fundacion.2626!_@aws-1-us-east-1.pooler.supabase.com:6543/postgres",
)

CAL_API_KEY = os.getenv("CAL_API_KEY", "cal_live_05087d22a1b45b6491878a31ae936af2")
CAL_API_VERSION_SLOTS = os.getenv("CAL_API_VERSION_SLOTS", "2024-09-04")
CAL_API_VERSION_BOOKINGS = os.getenv("CAL_API_VERSION_BOOKINGS", "2024-08-13")
CAL_USERNAME = os.getenv("CAL_USERNAME", "fundacionangelical-kwdgm7")
CAL_EVENT_SLUG = os.getenv("CAL_EVENT_SLUG", "consulta")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "America/Bogota")
