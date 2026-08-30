from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.storage.repository import repository
from app.api.routes import router as api_router
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode...")
    settings.init_directories()
    await repository.init_db()
    yield
    # Shutdown
    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    description="High-performance async checker for IP addresses, proxy servers, and VPN/V2Ray nodes with real-time UI.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)

# Mount Static Files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_index():
    """Serve the Web Dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": f"{settings.APP_NAME} API is active. Web UI not found."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
