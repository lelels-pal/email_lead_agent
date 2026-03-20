"""Email lead agent package."""

from email_lead_agent.lead_evaluator import (
    LeadEvaluation,
    evaluate_email_body,
    evaluate_email_body_sync,
)

__all__ = ["LeadEvaluation", "evaluate_email_body", "evaluate_email_body_sync"]
