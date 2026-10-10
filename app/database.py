import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_xlsx() -> str:
    """Workbook location: env override, repo data/, or the serverless bundle copy."""
    candidates = [
        os.environ.get("GHG_DATA_XLSX"),
        os.path.join(BASE_DIR, "data", "ghg_sheet.xlsx"),
        os.path.join(BASE_DIR, "api", "data", "ghg_sheet.xlsx"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[1]


DATA_XLSX = _resolve_xlsx()


def _resolve_db_path() -> str:
    """SQLite file location. On read-only filesystems (e.g. serverless), fall back to /tmp."""
    env_path = os.environ.get("GHG_DB_PATH")
    if env_path:
        return env_path
    default = os.path.join(BASE_DIR, "data", "ghg_platform.db")
    try:
        os.makedirs(os.path.dirname(default), exist_ok=True)
        with open(default, "a"):
            pass
        return default
    except OSError:
        return os.path.join(tempfile.gettempdir(), "ghg_platform.db")


def _build_engine():
    """DATABASE_URL (e.g. Supabase Postgres) when set; SQLite otherwise (local dev)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        if "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return create_engine(url, pool_pre_ping=True)
    return create_engine(f"sqlite:///{_resolve_db_path()}", connect_args={"check_same_thread": False})


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    # Lazy import avoids a circular dependency; seeding is race-safe and runs
    # once per process (also covers serverless platforms where ASGI lifespan
    # events do not fire).
    from .seed import ensure_seeded

    ensure_seeded()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
