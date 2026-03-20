import asyncio
import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from playwright.async_api import Error, Locator, Page, TimeoutError, async_playwright

from email_lead_agent.lead_evaluator import evaluate_email_body


@dataclass
class EmailContent:
    sender: str
    subject: str
    body: str


CONSENT_BUTTON_TEXTS = [
    "Accept all",
    "I agree",
    "Accept",
    "Yes, I agree",
]


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
    await email_field.wait_for(timeout=30_000)
    await email_field.fill(email)
    await page.get_by_role("button", name="Next").click()

    password_field = page.locator("input[type='password']")
    await password_field.wait_for(timeout=30_000)
    await password_field.fill(password)
    await page.get_by_role("button", name="Next").click()


async def wait_for_inbox(page: Page) -> None:
    await page.wait_for_url("**mail.google.com/**", timeout=60_000)
    inbox = page.get_by_role("main")
    await inbox.wait_for(timeout=60_000)


async def open_first_unread_email(page: Page) -> None:
    unread_row = page.locator("tr.zA.zE").first
    await unread_row.wait_for(timeout=30_000)
    await unread_row.click()


async def extract_open_email(page: Page) -> EmailContent:
    sender_selectors = [
        "span.gD",
        "h3 span[email]",
    ]
    subject_selectors = [
        "h2.hP",
        "div[role='main'] h2",
    ]
    body_selectors = [
        "div.a3s.aiL",
        "div.a3s",
        "div[role='listitem']",
    ]

    sender = await first_text(page, sender_selectors)
    subject = await first_text(page, subject_selectors)
    body = await first_text(page, body_selectors)

    return EmailContent(sender=sender, subject=subject, body=body)


async def draft_reply(page: Page, reply_text: str) -> None:
    reply_button = page.get_by_role("button", name="Reply").first
    if not await maybe_click(reply_button):
        fallback_selectors = [
            "div[role='button'][aria-label*='Reply']",
            "span[role='link'][data-tooltip*='Reply']",
            "div[command='rd']",
        ]
        for selector in fallback_selectors:
            locator = page.locator(selector).first
            if await maybe_click(locator):
                break
        else:
            raise RuntimeError("Could not find the Gmail reply button.")

    reply_box_selectors = [
        "div[aria-label='Message Body']",
        "div[role='textbox'][aria-label*='Message Body']",
        "div[role='textbox'][g_editable='true']",
    ]

    for selector in reply_box_selectors:
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


async def wait_for_draft_saved(page: Page) -> None:
    save_indicators = [
        "text=Saved to Drafts",
        "text=Saving...",
        "[role='alert']:has-text('Saved to Drafts')",
    ]

    for selector in save_indicators:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=5_000)
            if "Saving..." in selector:
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


async def main() -> None:
    load_dotenv()

    email = os.getenv("GMAIL_EMAIL")
    password = os.getenv("GMAIL_PASSWORD")
    headless = os.getenv("HEADLESS", "true").lower() == "true"

    if not email or not password:
        raise RuntimeError("Missing GMAIL_EMAIL or GMAIL_PASSWORD in .env")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await fill_google_login(page, email, password)
            await wait_for_inbox(page)
            await open_first_unread_email(page)
            email_content = await extract_open_email(page)
            lead_evaluation = await evaluate_email_body(email_content.body)

            print(f"Sender: {email_content.sender}")
            print(f"Subject: {email_content.subject}")
            print("Body:")
            print(email_content.body)
            print("Lead Evaluation:")
            print(json.dumps(lead_evaluation.model_dump(), indent=2))

            if lead_evaluation.is_lead:
                await draft_reply(page, lead_evaluation.suggested_reply)
                print("Draft reply saved in Gmail.")
            else:
                print("Email was not marked as a lead. No draft created.")
        finally:
            await context.close()
            await browser.close()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
