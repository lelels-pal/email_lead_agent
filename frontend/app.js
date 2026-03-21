const state = {
  emails: [],
  activity: [],
  selectedId: null,
  filter: "all",
  autoDraft: false,
  sessionActive: false,
  loadingAction: null,
  error: "",
  statusCopy: "Start with a live scan to pull the first unread Gmail message into the queue.",
};

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const message = payload?.detail || "The workspace could not complete that request.";
    throw new Error(message);
  }

  return payload;
}

function setLoading(action) {
  state.loadingAction = action;
  render(appRoot);
}

function clearLoading() {
  state.loadingAction = null;
  render(appRoot);
}

function selectedEmail() {
  return state.emails.find((email) => email.id === state.selectedId) ?? null;
}

function getVisibleEmails() {
  if (state.filter === "lead") {
    return state.emails.filter((email) => email.is_lead && email.status !== "archived");
  }

  if (state.filter === "review") {
    return state.emails.filter((email) => email.status === "review");
  }

  return state.emails;
}

function syncWorkspace(data) {
  state.emails = data.emails ?? [];
  state.activity = data.activity ?? [];
  state.sessionActive = data.session_active ?? false;
  state.selectedId = data.selected_id || state.emails[0]?.id || null;
}

async function loadWorkspace() {
  setLoading("bootstrap");
  try {
    const data = await apiRequest("/api/workspace");
    syncWorkspace(data);
    state.error = "";
    state.statusCopy =
      state.emails.length > 0
        ? "The operator queue reflects the latest live Gmail snapshot."
        : "Start with a live scan to pull the first unread Gmail message into the queue.";
  } catch (error) {
    state.error = error.message;
  } finally {
    clearLoading();
  }
}

async function runAction(action, request) {
  setLoading(action);
  try {
    const payload = await request();
    if (payload?.emails) {
      syncWorkspace(payload);
    } else {
      const refreshed = await apiRequest("/api/workspace");
      syncWorkspace(refreshed);
    }
    state.error = "";
    return payload;
  } catch (error) {
    state.error = error.message;
    throw error;
  } finally {
    clearLoading();
  }
}

async function scanInbox() {
  await runAction("scan", async () => {
    const result = await apiRequest("/api/agent/scan", {
      method: "POST",
      body: JSON.stringify({ auto_draft_if_lead: state.autoDraft }),
    });

    state.statusCopy = result.status === "draft"
      ? "A qualified lead was found and the reply was saved as a Gmail draft."
      : "A live email was scanned and is ready for operator review.";
    return result;
  });
}

async function saveDraft() {
  const email = selectedEmail();
  const editor = appRoot.querySelector("[data-reply-editor]");

  if (!email || !editor) {
    return;
  }

  await runAction("draft", async () => {
    const result = await apiRequest("/api/agent/draft", {
      method: "POST",
      body: JSON.stringify({ reply_text: editor.value.trim() }),
    });

    state.statusCopy = "The reply was saved to Gmail drafts for final human review.";
    return result;
  });
}

async function markForReview() {
  await runAction("review", async () => {
    const result = await apiRequest("/api/agent/review", { method: "POST", body: "{}" });
    state.statusCopy = "The current email was held in the queue for a human decision.";
    return result;
  });
}

async function archiveEmail() {
  await runAction("archive", async () => {
    const result = await apiRequest("/api/agent/archive", { method: "POST", body: "{}" });
    state.statusCopy = "The current email was archived from Gmail.";
    return result;
  });
}

async function closeSession() {
  await runAction("close", async () => {
    await apiRequest("/api/agent/close", { method: "POST", body: "{}" });
    state.statusCopy = "The Playwright Gmail session was closed.";
    return null;
  });
}

function updateStats(root) {
  root.querySelector("[data-stat-unread]").textContent = String(
    state.emails.filter((email) => email.status !== "archived").length,
  );
  root.querySelector("[data-stat-leads]").textContent = String(
    state.emails.filter((email) => email.is_lead).length,
  );
  root.querySelector("[data-stat-drafts]").textContent = String(
    state.emails.filter((email) => email.status === "draft").length,
  );
  root.querySelector("[data-stat-archived]").textContent = String(
    state.emails.filter((email) => email.status === "archived").length,
  );
}

function scoreClass(score) {
  if (score >= 8) return "score-pill";
  return "score-pill score-pill-muted";
}

function statusTag(email) {
  if (email.status === "draft") {
    return '<span class="tag tag-lead">Draft ready</span>';
  }

  if (email.status === "archived") {
    return '<span class="tag tag-neutral">Archived</span>';
  }

  if (email.is_lead) {
    return '<span class="tag tag-lead">Qualified lead</span>';
  }

  return '<span class="tag tag-review">Needs review</span>';
}

function detailBadge(email) {
  if (!email) return { text: "Waiting", className: "badge" };
  if (email.status === "draft") return { text: "Draft", className: "badge badge-success" };
  if (email.status === "archived") return { text: "Archived", className: "badge" };
  return { text: email.is_lead ? "Lead" : "Review", className: `badge ${email.is_lead ? "badge-success" : ""}`.trim() };
}

function renderMailList(root) {
  const container = root.querySelector("[data-mail-list]");
  const visibleEmails = getVisibleEmails();

  if (!visibleEmails.some((email) => email.id === state.selectedId)) {
    state.selectedId = visibleEmails[0]?.id ?? null;
  }

  if (visibleEmails.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <strong>No live emails yet</strong>
        <p>Run a scan to bring the first unread Gmail message into this queue.</p>
        <button class="button button-primary" type="button" data-empty-scan>Scan unread email</button>
      </div>
    `;
    container.querySelector("[data-empty-scan]")?.addEventListener("click", scanInbox);
    return;
  }

  container.innerHTML = visibleEmails
    .map(
      (email) => `
        <button class="mail-card ${email.id === state.selectedId ? "mail-card-active" : ""}" data-email-id="${email.id}">
          <div class="mail-card-top">
            <strong>${email.sender.split("<")[0].trim()}</strong>
            <span class="${scoreClass(email.score)}">${email.score}</span>
          </div>
          <p class="mail-card-subject">${email.subject}</p>
          <p class="mail-card-snippet">${email.body.slice(0, 118)}${email.body.length > 118 ? "..." : ""}</p>
          <div class="mail-card-tags">
            ${statusTag(email)}
            <span class="tag tag-neutral">${email.action_taken.replaceAll("_", " ")}</span>
          </div>
        </button>
      `,
    )
    .join("");

  container.querySelectorAll("[data-email-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.getAttribute("data-email-id");
      render(root);
    });
  });
}

function renderDetails(root) {
  const email = selectedEmail();
  const badge = root.querySelector("[data-detail-badge]");
  const editor = root.querySelector("[data-reply-editor]");
  const buttons = root.querySelectorAll("[data-action]");

  if (!email) {
    root.querySelector("[data-detail-subject]").textContent = "Select an email";
    root.querySelector("[data-detail-sender]").textContent = "—";
    root.querySelector("[data-detail-score]").textContent = "—";
    root.querySelector("[data-detail-decision]").textContent = "—";
    root.querySelector("[data-detail-reasoning]").textContent =
      "Run a live scan to inspect the structured evaluation.";
    root.querySelector("[data-detail-body]").textContent =
      "The Gmail message body will appear here after the first unread email is scanned.";
    badge.textContent = "Waiting";
    badge.className = "badge";
    editor.value = "";
    buttons.forEach((button) => {
      button.disabled = true;
    });
    return;
  }

  root.querySelector("[data-detail-subject]").textContent = email.subject;
  root.querySelector("[data-detail-sender]").textContent = email.sender;
  root.querySelector("[data-detail-score]").textContent = `${email.score}/10`;
  root.querySelector("[data-detail-decision]").textContent = email.is_lead ? "Lead" : "Not a lead";
  root.querySelector("[data-detail-reasoning]").textContent = email.reasoning;
  root.querySelector("[data-detail-body]").textContent = email.body;

  const nextBadge = detailBadge(email);
  badge.textContent = nextBadge.text;
  badge.className = nextBadge.className;
  editor.value = email.suggested_reply;

  buttons.forEach((button) => {
    button.disabled = Boolean(state.loadingAction);
    button.onclick = async () => {
      const action = button.getAttribute("data-action");
      if (action === "draft") {
        await saveDraft();
      }
      if (action === "review") {
        await markForReview();
      }
      if (action === "archive") {
        await archiveEmail();
      }
    };
  });
}

function renderActivity(root) {
  const container = root.querySelector("[data-activity-list]");

  if (state.activity.length === 0) {
    container.innerHTML = `
      <div class="empty-state empty-state-subtle">
        <strong>No activity yet</strong>
        <p>The timeline will update after the first live scan or operator action.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = state.activity
    .slice(0, 6)
    .map(
      (entry) => `
        <article class="timeline-entry">
          <span class="timeline-dot"></span>
          <div>
            <strong>${entry.title}</strong>
            <p>${entry.body}</p>
            <p class="panel-label">${entry.time}</p>
          </div>
        </article>
      `,
    )
    .join("");
}

function bindFilters(root) {
  root.querySelectorAll("[data-filter]").forEach((button) => {
    const isActive = button.getAttribute("data-filter") === state.filter;
    button.classList.toggle("filter-button-active", isActive);

    button.onclick = () => {
      state.filter = button.getAttribute("data-filter");
      render(root);
    };
  });
}

function bindControls(root) {
  const runButton = root.querySelector("[data-run-scan]");
  const closeButton = root.querySelector("[data-close-session]");
  const toggle = root.querySelector("[data-auto-draft]");

  runButton.textContent = state.loadingAction === "scan" ? "Scanning..." : "Scan unread email";
  closeButton.textContent = state.loadingAction === "close" ? "Closing..." : "Close browser";

  runButton.disabled = Boolean(state.loadingAction);
  closeButton.disabled = Boolean(state.loadingAction) || !state.sessionActive;

  toggle.checked = state.autoDraft;
  toggle.disabled = Boolean(state.loadingAction);
  toggle.onchange = () => {
    state.autoDraft = toggle.checked;
  };

  runButton.onclick = scanInbox;
  closeButton.onclick = closeSession;
}

function renderStatus(root) {
  const indicator = root.querySelector("[data-session-indicator]");
  const copy = root.querySelector("[data-status-copy]");
  const error = root.querySelector("[data-error-text]");

  if (state.loadingAction === "scan") {
    indicator.textContent = "Scanning live inbox";
  } else if (state.sessionActive) {
    indicator.textContent = "Browser connected";
  } else {
    indicator.textContent = "Idle";
  }

  copy.textContent = state.statusCopy;

  if (state.error) {
    error.hidden = false;
    error.textContent = state.error;
  } else {
    error.hidden = true;
    error.textContent = "";
  }
}

function render(root) {
  if (!root) return;
  updateStats(root);
  bindFilters(root);
  bindControls(root);
  renderStatus(root);
  renderMailList(root);
  renderDetails(root);
  renderActivity(root);
}

const appRoot = document.querySelector("[data-workspace-app]");
if (appRoot) {
  loadWorkspace();
}
