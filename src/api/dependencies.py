"""
Dependency injection container and singleton instances for RevPulse API.
"""

from src.services.ai_engine import RevPulseAIEngine
from src.services.audit_logger import AuditLogger
from src.services.escalation_manager import HumanEscalationManager
from src.services.guardrails import ComplianceGuardrailsEngine
from src.services.normalizer import AccountingDataNormalizer
from src.services.orchestrator import ARPipelineOrchestrator
from src.services.payment_gateway import PaymentGatewayService
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager


# Singletons for FastAPI dependency injection
audit_logger = AuditLogger()
state_manager = ConversationStateManager()
payment_gateway = PaymentGatewayService()
guardrails_engine = ComplianceGuardrailsEngine()
escalation_manager = HumanEscalationManager()
ai_engine = RevPulseAIEngine()
normalizer = AccountingDataNormalizer()
orchestrator = ARPipelineOrchestrator(normalizer=normalizer)

recovery_coordinator = RecoveryLoopCoordinator(
    ai_engine=ai_engine,
    state_manager=state_manager,
    payment_gateway=payment_gateway,
    guardrails=guardrails_engine,
    audit_logger=audit_logger,
    escalation_manager=escalation_manager,
)


def get_audit_logger() -> AuditLogger:
    return audit_logger


def get_state_manager() -> ConversationStateManager:
    return state_manager


def get_payment_gateway() -> PaymentGatewayService:
    return payment_gateway


def get_orchestrator() -> ARPipelineOrchestrator:
    return orchestrator


def get_ai_engine() -> RevPulseAIEngine:
    return ai_engine


def get_recovery_coordinator() -> RecoveryLoopCoordinator:
    return recovery_coordinator

