"""FastAPI application for view-fn-hist web interface."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env file before other imports
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import router

app = FastAPI(
    title="Function Evolution Viewer",
    description="View the git history of a specific function",
    version="0.1.0",
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Mount frontend static files if they exist
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend"
    )


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the web server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
