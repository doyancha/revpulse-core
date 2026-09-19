"""
Routers package init for RevPulse API.
"""

from src.api.routers.accounting_webhooks import router as accounting_router
from src.api.routers.comm_webhooks import router as comm_router
from src.api.routers.payment_webhooks import router as payment_router
from src.api.routers.audit_routes import router as audit_router

__all__ = [
    "accounting_router",
    "comm_router",
    "payment_router",
    "audit_router",
]
