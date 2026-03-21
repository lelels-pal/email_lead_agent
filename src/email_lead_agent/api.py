from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from email_lead_agent.agent_service import AgentEmailResult, GmailAgentSession
from email_lead_agent.lead_evaluator import evaluate_email_body


class ScanRequest(BaseModel):
    auto_draft_if_lead: bool = Field(default=False)


class DraftRequest(BaseModel):
    reply_text: str | None = None


class EvaluateRequest(BaseModel):
    email_body: str = Field(min_length=1)


class WorkspaceEmail(BaseModel):
    id: str
    sender: str
    subject: str
    body: str
    score: int
    is_lead: bool
    reasoning: str
    suggested_reply: str
    status: str
    action_taken: str


class ActivityEntry(BaseModel):
    title: str
    body: str
    time: str


class WorkspaceResponse(BaseModel):
    emails: list[WorkspaceEmail]
    activity: list[ActivityEntry]
    session_active: bool
    selected_id: str | None


BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

agent_lock = asyncio.Lock()
agent_session = GmailAgentSession()
workspace_emails: list[WorkspaceEmail] = []
workspace_activity: list[ActivityEntry] = []
selected_id: str | None = None


def now_label() -> str:
    return datetime.now().strftime("%b %d, %I:%M %p")


def to_workspace_email(result: AgentEmailResult) -> WorkspaceEmail:
    return WorkspaceEmail(**result.to_dict())


def upsert_email(result: AgentEmailResult) -> WorkspaceEmail:
    global selected_id

    email = to_workspace_email(result)
    for index, existing in enumerate(workspace_emails):
        if existing.id == email.id:
            workspace_emails[index] = email
            selected_id = email.id
            return email

    workspace_emails.insert(0, email)
    del workspace_emails[12:]
    selected_id = email.id
    return email


def add_activity(title: str, body: str) -> None:
    workspace_activity.insert(0, ActivityEntry(title=title, body=body, time=now_label()))
    del workspace_activity[12:]


def build_workspace_response() -> WorkspaceResponse:
    return WorkspaceResponse(
        emails=workspace_emails,
        activity=workspace_activity,
        session_active=agent_session.is_active,
        selected_id=selected_id,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await agent_session.close()


app = FastAPI(title="Email Lead Agent", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/workspace", include_in_schema=False)
async def workspace() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "workspace.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspace", response_model=WorkspaceResponse)
async def get_workspace() -> WorkspaceResponse:
    return build_workspace_response()


@app.post("/api/evaluate")
async def evaluate(request: EvaluateRequest) -> dict[str, object]:
    evaluation = await evaluate_email_body(request.email_body)
    return evaluation.model_dump()


@app.post("/api/agent/scan", response_model=WorkspaceEmail)
async def scan_first_unread(request: ScanRequest) -> WorkspaceEmail:
    try:
        async with agent_lock:
            result = await agent_session.scan_first_unread(
                auto_draft_if_lead=request.auto_draft_if_lead
            )
            email = upsert_email(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sender_name = result.sender.split("<")[0].strip()
    if result.status == "draft":
        add_activity(
            "Draft prepared in Gmail",
            f"{sender_name} was scored {result.score}/10 and saved to drafts.",
        )
    else:
        add_activity(
            "Live inbox scan complete",
            f"{sender_name} was reviewed with a {result.score}/10 lead score.",
        )
    return email


@app.post("/api/agent/draft", response_model=WorkspaceEmail)
async def draft_current(request: DraftRequest) -> WorkspaceEmail:
    try:
        async with agent_lock:
            result = await agent_session.save_draft(request.reply_text)
            email = upsert_email(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sender_name = result.sender.split("<")[0].strip()
    add_activity(
        "Draft saved",
        f"{sender_name} now has a draft reply staged in Gmail.",
    )
    return email


@app.post("/api/agent/archive", response_model=WorkspaceEmail)
async def archive_current() -> WorkspaceEmail:
    try:
        async with agent_lock:
            result = await agent_session.archive_current()
            email = upsert_email(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sender_name = result.sender.split("<")[0].strip()
    add_activity(
        "Email archived",
        f"{sender_name} was archived from the Gmail inbox.",
    )
    return email


@app.post("/api/agent/review", response_model=WorkspaceEmail)
async def mark_review() -> WorkspaceEmail:
    try:
        async with agent_lock:
            result = await agent_session.mark_current_for_review()
            email = upsert_email(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sender_name = result.sender.split("<")[0].strip()
    add_activity(
        "Held for review",
        f"{sender_name} remains in the operator queue for a human decision.",
    )
    return email


@app.post("/api/agent/close")
async def close_session() -> dict[str, bool]:
    global selected_id

    async with agent_lock:
        await agent_session.close()
    selected_id = workspace_emails[0].id if workspace_emails else None
    add_activity("Browser session closed", "The Gmail automation session was safely closed.")
    return {"closed": True}


def cli() -> None:
    uvicorn.run("email_lead_agent.api:app", host="127.0.0.1", port=8000, reload=False)
