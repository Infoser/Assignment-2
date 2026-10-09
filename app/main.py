from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import BASE_DIR
from .routers import analytics, metrics, records
from .seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_seed()
    yield


app = FastAPI(
    title="Carbon Emissions Reporting Platform",
    description=(
        "GHG Protocol platform prototype: tracks, calculates and reports Scope 1 & 2 "
        "(and Scope 3) emissions with versioned emission factors, an override audit "
        "trail and advanced analytics (YoY, intensity, hotspots, monthly trends)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(records.router)
app.include_router(analytics.router)
app.include_router(metrics.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


static_dir = Path(BASE_DIR) / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
