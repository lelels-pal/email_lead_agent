# Email Lead Agent

Minimal Python project scaffold for a Gmail-reading agent powered by Playwright, LangChain, and OpenRouter.

## Frontend

A project-local frontend now lives in [`frontend/`](./frontend):

- [`frontend/index.html`](./frontend/index.html) for the product overview
- [`frontend/workspace.html`](./frontend/workspace.html) for the operator workspace
- [`frontend/styles.css`](./frontend/styles.css) for the shared design system
- [`frontend/app.js`](./frontend/app.js) for workspace interactions

To preview it locally:

`python -m http.server 8000 -d frontend`

Then open:

- `http://localhost:8000/`
- `http://localhost:8000/workspace.html`

## Setup

1. Create and activate a virtual environment.
2. Install the project in editable mode:
   `pip install -e .`
3. Install the Chromium browser for Playwright:
   `playwright install chromium`
4. Copy `.env.example` to `.env` and fill in your Gmail credentials.
5. Add your `OPENROUTER_API_KEY` to `.env`.

## Run

`python -m email_lead_agent.gmail_reader`

Or use the console script:

`read-gmail`

## Lead Evaluation Module

The LangChain evaluator can be imported from `email_lead_agent.lead_evaluator` and used to score an email body as a B2B software lead while generating a two-sentence reply draft.

By default the evaluator uses `OPENROUTER_MODEL=openrouter/free`, which routes to OpenRouter's free model pool. You can set a specific `:free` model in `.env` if you want more consistent behavior.
