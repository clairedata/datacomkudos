"""
PROJECT: Datacom Kudos System
FILE: src/main.py
DESCRIPTION: FastAPI Application Entry Point.
             Configures CORS, registers REST API endpoints (v1),
             enforces RFC 7807 compliant error format, mounts static UI files,
             and guarantees database schema initialization on startup.
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.db.database import init_db
from src.services.kudos_service import KudosException, get_utc_now_iso
from src.api.routes import router as api_router

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager:
    Ensures relational SQLite database and seeds are initialized on startup.
    """
    init_db()
    yield


app = FastAPI(
    title="Datacom Kudos System",
    description="Graduate Developer Assessment: Employee Recognition & Content Moderation Portal",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure Cross-Origin Resource Sharing (CORS) for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST API v1 routes
app.include_router(api_router)


# ============================================================================
# RFC 7807 STANDARDIZED ERROR HANDLERS
# ============================================================================

@app.exception_handler(KudosException)
async def kudos_domain_exception_handler(request: Request, exc: KudosException):
    """
    Translates internal domain business rule exceptions into RFC 7807 JSON responses.
    """
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code_map.get(exc.status_code, "ERROR"),
                "message": exc.message,
                "status": exc.status_code,
                "details": exc.details,
                "timestamp": get_utc_now_iso()
            }
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Translates FastAPI/Starlette HTTP exceptions into RFC 7807 JSON responses.
    """
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail
    details = []

    if isinstance(exc.detail, dict):
        error_code = exc.detail.get("code", error_code)
        message = exc.detail.get("message", str(exc.detail))
        details = exc.detail.get("details", [])

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(message),
                "status": exc.status_code,
                "details": details,
                "timestamp": get_utc_now_iso()
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Translates Pydantic schema validation failures into RFC 7807 JSON responses.
    """
    details = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field_name = str(loc[-1]) if loc else "body"
        details.append({
            "field": field_name,
            "issue": err.get("msg", "Invalid value.")
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request payload validation failed.",
                "status": 422,
                "details": details,
                "timestamp": get_utc_now_iso()
            }
        }
    )


# ============================================================================
# STATIC FILES & ROOT ROUTE
# ============================================================================

static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", tags=["Health"])
def root_endpoint():
    """
    Serves SPA frontend if present, otherwise returns API health status.
    """
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "name": "Datacom Kudos System API",
        "status": "operational",
        "docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
