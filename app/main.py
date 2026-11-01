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
    version=settings.VERSION,
    docs_url="/api/docs"
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

from fastapi import Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.ingestion.otlp_handler import process_otlp_http_bytes, IngestionError
from app.ingestion.compatibility import get_compatibility_matrix

app.include_router(router)

@app.post("/v1/traces")
async def otlp_traces_endpoint(request: Request, db: Session = Depends(get_db)):
    """
    Standard OpenTelemetry OTLP HTTP/JSON trace ingestion endpoint.
    Computes cryptographic SHA-256 digest of exact raw payload bytes before normalization.
    """
    raw_bytes = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    company_id = request.headers.get("x-company-id") or request.query_params.get("company_id")
    try:
        res = process_otlp_http_bytes(db, raw_bytes, content_type=content_type, company_id=company_id)
        return JSONResponse(status_code=200, content=res.to_dict())
    except IngestionError as ie:
        return JSONResponse(status_code=ie.status_code, content={"error": ie.message, "status": "FAILED"})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": f"Internal ingestion error: {str(exc)}", "status": "FAILED"})

@app.get("/v1/compatibility")
def get_otlp_compatibility_matrix():
    """
    Returns the OpenTelemetry GenAI integration compatibility matrix.
    """
    return get_compatibility_matrix()

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def serve_landing_page():
    """Serves Experience A: The Public Marketing Landing Page."""
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "landing.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    index_path = os.path.join(os.path.dirname(__file__), "ui", "templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {
        "name": settings.PROJECT_NAME,
        "slogan": settings.PROJECT_SLOGAN,
        "version": settings.VERSION,
        "docs_url": "/api/docs"
    }

@app.get("/product")
def serve_product_page():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "product.html")
    return FileResponse(path, media_type="text/html")

@app.get("/capabilities")
def serve_capabilities_page():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "capabilities.html")
    return FileResponse(path, media_type="text/html")

@app.get("/how-it-works")
def serve_how_it_works_page():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "how_it_works.html")
    return FileResponse(path, media_type="text/html")

@app.get("/trust")
def serve_trust_page():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "trust.html")
    return FileResponse(path, media_type="text/html")

@app.get("/docs")
def serve_docs_hub():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "docs.html")
    return FileResponse(path, media_type="text/html")

@app.get("/get-started")
def serve_get_started_page():
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "get_started.html")
    return FileResponse(path, media_type="text/html")

@app.get("/cockpit")
def serve_legacy_cockpit():
    index_path = os.path.join(os.path.dirname(__file__), "ui", "templates", "index.html")
    return FileResponse(index_path, media_type="text/html")

@app.get("/app")
@app.get("/app/{full_path:path}")
def serve_application_workspace(full_path: str = ""):
    path = os.path.join(os.path.dirname(__file__), "ui", "templates", "app.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    index_path = os.path.join(os.path.dirname(__file__), "ui", "templates", "index.html")
    return FileResponse(index_path, media_type="text/html")

@app.get("/api/info")
def root_info():
    return {
        "name": settings.PROJECT_NAME,
        "slogan": settings.PROJECT_SLOGAN,
        "version": settings.VERSION,
        "docs_url": "/api/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
