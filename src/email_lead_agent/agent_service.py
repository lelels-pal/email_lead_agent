from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

from dotenv import load_dotenv
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error,
    Locator,
    Page,
    Playwright,
    TimeoutError,
    async_playwright,
)

from email_lead_agent.lead_evaluator import LeadEvaluation, evaluate_email_body


CONSENT_BUTTON_TEXTS = [
    "Accept all",
    "I agree",
    "Accept",
    "Yes, I agree",
]


@dataclass
class EmailContent:
    sender: str
    subject: str
    body: str


@dataclass
class AgentEmailResult:
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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


async def maybe_click(locator: Locator) -> bool:
    try:
        await locator.click(timeout=2_000)
        return True
    except (TimeoutError, Error):
        return False


async def dismiss_cookie_consent(page: Page) -> None:
    for frame in page.frames:
        for label in CONSENT_BUTTON_TEXTS:
            locator = frame.get_by_role("button", name=label)
            if await maybe_click(locator):
                return

    selectors = [
        "button:has-text('Accept all')",
        "button:has-text('I agree')",
        "button:has-text('Accept')",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if await maybe_click(locator):
            return


async def fill_google_login(page: Page, email: str, password: str) -> None:
    await page.goto("https://mail.google.com/", wait_until="domcontentloaded")
    await dismiss_cookie_consent(page)

    email_field = page.locator("input[type='email']")
    try:
        await email_field.wait_for(timeout=8_000)
    except TimeoutError:
        return

    await email_field.fill(email)
    await page.get_by_role("button", name="Next").click()

    password_field = page.locator("input[type='password']")
    await password_field.wait_for(timeout=30_000)
    await password_field.fill(password)
    await page.get_by_role("button", name="Next").click()


async def wait_for_inbox(page: Page) -> None:
    await page.wait_for_url("**mail.google.com/**", timeout=60_000)
    await page.get_by_role("main").wait_for(timeout=60_000)


async def go_to_inbox(page: Page) -> None:
    await page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")
    await wait_for_inbox(page)


async def open_first_unread_email(page: Page) -> None:
    unread_row = page.locator("tr.zA.zE").first
    try:
        await unread_row.wait_for(timeout=15_000)
    except TimeoutError as exc:
        raise RuntimeError("No unread emails were found in Gmail.") from exc
    await unread_row.click()


async def extract_open_email(page: Page) -> EmailContent:
    sender = await first_text(page, ["span.gD", "h3 span[email]"])
    subject = await first_text(page, ["h2.hP", "div[role='main'] h2"])
    body = await first_text(page, ["div.a3s.aiL", "div.a3s", "div[role='listitem']"])
    return EmailContent(sender=sender, subject=subject, body=body)


async def draft_reply(page: Page, reply_text: str) -> None:
    reply_button = page.get_by_role("button", name="Reply").first
    if not await maybe_click(reply_button):
        for selector in [
            "div[role='button'][aria-label*='Reply']",
            "span[role='link'][data-tooltip*='Reply']",
            "div[command='rd']",
        ]:
            if await maybe_click(page.locator(selector).first):
                break
        else:
            raise RuntimeError("Could not find the Gmail reply button.")

    for selector in [
        "div[aria-label='Message Body']",
        "div[role='textbox'][aria-label*='Message Body']",
        "div[role='textbox'][g_editable='true']",
    ]:
        reply_box = page.locator(selector).last
        try:
            await reply_box.wait_for(timeout=10_000)
            await reply_box.click()
            await reply_box.fill(reply_text)
            await wait_for_draft_saved(page)
            return
        except (TimeoutError, Error):
            continue

    raise RuntimeError("Could not find the Gmail reply editor.")


async def archive_open_email(page: Page) -> None:
    archive_button = page.get_by_role("button", name="Archive").first
    if not await maybe_click(archive_button):
        for selector in [
            "div[role='button'][aria-label*='Archive']",
            "div[data-tooltip*='Archive']",
            "div[command='tr']",
        ]:
            if await maybe_click(page.locator(selector).first):
                return
        raise RuntimeError("Could not find the Gmail archive button.")


async def wait_for_draft_saved(page: Page) -> None:
    for selector in [
        "text=Saved to Drafts",
        "text=Saving...",
        "[role='alert']:has-text('Saved to Drafts')",
    ]:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=5_000)
            if selector == "text=Saving...":
                await page.locator("text=Saved to Drafts").first.wait_for(timeout=10_000)
            return
        except (TimeoutError, Error):
            continue

    await page.wait_for_timeout(3_000)


async def first_text(page: Page, selectors: list[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=10_000)
            text = (await locator.inner_text()).strip()
            if text:
                return text
        except (TimeoutError, Error):
            continue
    raise RuntimeError(f"Could not extract text using selectors: {selectors}")


def build_email_id(sender: str, subject: str) -> str:
    base = f"{sender}-{subject}".lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return cleaned or "email-item"


def build_result(
    email_content: EmailContent,
    evaluation: LeadEvaluation,
    *,
    status: str,
    action_taken: str,
) -> AgentEmailResult:
    return AgentEmailResult(
        id=build_email_id(email_content.sender, email_content.subject),
        sender=email_content.sender,
        subject=email_content.subject,
        body=email_content.body,
        score=evaluation.score,
        is_lead=evaluation.is_lead,
        reasoning=evaluation.reasoning,
        suggested_reply=evaluation.suggested_reply,
        status=status,
        action_taken=action_taken,
    )


class GmailAgentSession:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.current_email: AgentEmailResult | None = None
        self._gmail_email: str | None = None
        self._gmail_password: str | None = None
        self._headless = True

    @property
    def is_active(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    async def ensure_started(self) -> None:
        load_dotenv()

        self._gmail_email = os.getenv("GMAIL_EMAIL")
        self._gmail_password = os.getenv("GMAIL_PASSWORD")
        self._headless = os.getenv("HEADLESS", "true").lower() == "true"

        if not self._gmail_email or not self._gmail_password:
            raise RuntimeError("Missing GMAIL_EMAIL or GMAIL_PASSWORD in .env")

        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
        if self._context is None:
            self._context = await self._browser.new_context()
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()

    async def scan_first_unread(self, *, auto_draft_if_lead: bool = False) -> AgentEmailResult:
        await self.ensure_started()
        page = self._require_page()

        await fill_google_login(page, self._gmail_email or "", self._gmail_password or "")
        await go_to_inbox(page)
        await open_first_unread_email(page)

        email_content = await extract_open_email(page)
        evaluation = await evaluate_email_body(email_content.body)

        result = build_result(
            email_content,
            evaluation,
            status="lead" if evaluation.is_lead else "review",
            action_taken="scanned",
        )
        self.current_email = result

        if auto_draft_if_lead and result.is_lead:
            return await self.save_draft()

        return result

    async def save_draft(self, reply_text: str | None = None) -> AgentEmailResult:
        if self.current_email is None:
            raise RuntimeError("No email is loaded. Run a live scan first.")

        page = self._require_page()
        reply_to_save = (reply_text or self.current_email.suggested_reply).strip()
        if not reply_to_save:
            raise RuntimeError("Reply text is empty.")

        await draft_reply(page, reply_to_save)
        self.current_email.suggested_reply = reply_to_save
        self.current_email.status = "draft"
        self.current_email.action_taken = "draft_saved"
        return self.current_email

    async def archive_current(self) -> AgentEmailResult:
        if self.current_email is None:
            raise RuntimeError("No email is loaded. Run a live scan first.")

        page = self._require_page()
        await archive_open_email(page)
        self.current_email.status = "archived"
        self.current_email.action_taken = "archived"
        return self.current_email

    async def mark_current_for_review(self) -> AgentEmailResult:
        if self.current_email is None:
            raise RuntimeError("No email is loaded. Run a live scan first.")

        self.current_email.status = "review"
        self.current_email.action_taken = "marked_for_review"
        return self.current_email

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self.current_email = None

    def _require_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise RuntimeError("Browser session is not active.")
        return self._page


async def run_single_pass(*, auto_draft_if_lead: bool = True) -> AgentEmailResult:
    session = GmailAgentSession()
    try:
        return await session.scan_first_unread(auto_draft_if_lead=auto_draft_if_lead)
    finally:
        await session.close()
