from __future__ import annotations

import asyncio
import json
import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, Field


SYSTEM_PROMPT = """You are a strict B2B software sales evaluator.

Your job is to review inbound email body text and determine whether the sender is a legitimate potential business lead for a software product.

Evaluation standards:
- Favor real buying signals such as clear business context, a company or team need, a software problem to solve, timeline, budget, decision-making authority, procurement intent, or a request for pricing, demo, integration, onboarding, or next steps.
- Reject emails that are personal, vague, spammy, irrelevant, job applications, support-only requests, partnership pitches without buying intent, investor outreach, newsletters, or cold solicitations from vendors.
- Be conservative. If the email does not show plausible B2B software purchase intent, mark it as not a lead.
- The score must be an integer from 1 to 10 where 1 means clearly not a lead and 10 means highly qualified and ready for sales follow-up.
- The reply must be exactly 2 sentences, polite, professional, and appropriate for email.
- If the sender is not a valid lead, the reply should still be courteous and brief without inventing product claims or offering discounts.

Return output that matches the required schema exactly."""


class LeadEvaluation(BaseModel):
    score: int = Field(
        description="Lead quality score from 1 to 10 inclusive.",
        ge=1,
        le=10,
    )
    is_lead: bool = Field(
        description="True when the email reflects likely B2B software buying intent."
    )
    reasoning: str = Field(
        description="Short explanation of why the email was or was not treated as a lead."
    )
    suggested_reply: str = Field(
        description="A polite professional email reply in exactly 2 sentences."
    )


def build_lead_evaluator(model: str | None = None, temperature: float = 0):
    load_dotenv()

    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("Missing OPENROUTER_API_KEY in .env")

    resolved_model = model or os.getenv("OPENROUTER_MODEL", "openrouter/free")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "Evaluate this inbound email body and return the structured result.\n\n"
                "Email body:\n{email_body}",
            ),
        ]
    )

    llm = ChatOpenRouter(
        model=resolved_model,
        temperature=temperature,
        max_retries=2,
    )
    return prompt | llm.with_structured_output(
        LeadEvaluation,
        method="json_schema",
        strict=True,
    )


async def evaluate_email_body(email_body: str) -> LeadEvaluation:
    chain = build_lead_evaluator()
    return await chain.ainvoke({"email_body": email_body})


def evaluate_email_body_sync(email_body: str) -> LeadEvaluation:
    return asyncio.run(evaluate_email_body(email_body))


async def evaluate_email_body_json(email_body: str) -> str:
    evaluation = await evaluate_email_body(email_body)
    return json.dumps(evaluation.model_dump(), indent=2)


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate an email body as a B2B software lead."
    )
    parser.add_argument("email_body", help="The email body text to evaluate.")
    args = parser.parse_args()
    print(asyncio.run(evaluate_email_body_json(args.email_body)))


if __name__ == "__main__":
    cli()
