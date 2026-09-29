import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.db.session import init_db
from app.api.routes import router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_SLOGAN,
    version=settings.VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets for interactive cockpit
static_dir = os.path.join(os.path.dirname(__file__), "ui", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(router)

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def serve_dashboard():
    """Serves the interactive due diligence cockpit UI."""
    index_path = os.path.join(os.path.dirname(__file__), "ui", "templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {
        "name": settings.PROJECT_NAME,
        "slogan": settings.PROJECT_SLOGAN,
        "version": settings.VERSION,
        "docs_url": "/docs"
    }

@app.get("/api/info")
def root_info():
    return {
        "name": settings.PROJECT_NAME,
        "slogan": settings.PROJECT_SLOGAN,
        "version": settings.VERSION,
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
