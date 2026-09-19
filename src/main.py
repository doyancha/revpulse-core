"""
Main entry point for RevPulse Autonomous AR Recovery Engine API Server.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.accounting_webhooks import router as accounting_router
from src.api.routers.comm_webhooks import router as comm_router
from src.api.routers.payment_webhooks import router as payment_router
from src.api.routers.audit_routes import router as audit_router
from src.api.routers.dashboard_routes import router as dashboard_router
from src.api.dependencies import (
    orchestrator,
    state_manager,
    audit_logger,
    recovery_coordinator,
)
from src.database.db import init_db
from src.services.scheduler import ARSchedulerService

scheduler_service = ARSchedulerService(
    orchestrator=orchestrator,
    state_manager=state_manager,
    audit_logger=audit_logger,
    recovery_coordinator=recovery_coordinator,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler managing database initialization and background scheduler."""
    init_db()
    scheduler_service.start()
    yield
    scheduler_service.shutdown()


app = FastAPI(
    title="RevPulse AR Engine",
    version="1.0.0",
    description="Autonomous AR Recovery Engine & Webhooks Gateway powered by Gemini",
    lifespan=lifespan,
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 Routers
app.include_router(accounting_router, prefix="/api/v1")
app.include_router(comm_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Service health check endpoint.
    """
    return {
        "status": "healthy",
        "service": "RevPulse Core",
        "version": "1.0.0",
    }
