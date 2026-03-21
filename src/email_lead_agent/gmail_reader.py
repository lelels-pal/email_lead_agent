import asyncio
import json
from email_lead_agent.agent_service import run_single_pass


async def main() -> None:
    result = await run_single_pass(auto_draft_if_lead=True)

    print(f"Sender: {result.sender}")
    print(f"Subject: {result.subject}")
    print("Body:")
    print(result.body)
    print("Lead Evaluation:")
    print(
        json.dumps(
            {
                "score": result.score,
                "is_lead": result.is_lead,
                "reasoning": result.reasoning,
                "suggested_reply": result.suggested_reply,
                "status": result.status,
                "action_taken": result.action_taken,
            },
            indent=2,
        )
    )


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
