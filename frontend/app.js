const emails = [
  {
    id: "northline-logistics",
    sender: "Marta Castillo <marta@northline-logistics.com>",
    subject: "Need pricing for a 12-seat rollout next month",
    body:
      "Hi team, we are reviewing tools for our customer support operation and need pricing for around 12 seats. If your product supports Gmail-based triage and Slack notifications, we would like to see a short demo and understand onboarding time this month.",
    score: 9,
    isLead: true,
    status: "draft",
    reasoning:
      "Clear B2B buying intent is present: team size, use case, timeline, and a direct request for pricing plus a demo.",
    reply:
      "Thanks for reaching out, Marta. We can support a 12-seat rollout and would be happy to share pricing along with a short demo tailored to your support workflow.",
    stageLabel: "Qualified lead",
  },
  {
    id: "acme-ops",
    sender: "Jordan Lee <jordan@acmeops.io>",
    subject: "Question about Slack integration and a pilot",
    body:
      "We are exploring whether your lead qualification flow could help our outbound team handle inbound requests. Can you confirm whether alerts can be reviewed in Slack and whether we could run a small pilot for our revops team in the next few weeks?",
    score: 7,
    isLead: true,
    status: "review",
    reasoning:
      "The sender shows plausible buying intent and a clear software use case, but the scope and decision process still need confirmation.",
    reply:
      "Thanks for the note, Jordan. Yes, we can support a pilot workflow and would be glad to walk through how Slack review fits into an inbound qualification process for your revops team.",
    stageLabel: "Needs review",
  },
  {
    id: "helpdesk-support",
    sender: "Dana Rivers <dana@helpdesksupport.net>",
    subject: "Issue with an old sample account",
    body:
      "Hello, I found an older sample login from a talk and wanted to ask if that environment is still active. If not, could you point me to the current documentation?",
    score: 3,
    isLead: false,
    status: "review",
    reasoning:
      "This message reads as a support request and does not contain real purchase intent, budget, or evaluation context.",
    reply:
      "Thanks for reaching out, Dana. That request looks closer to a support question, so please check the latest documentation and reply with any account details if you still need help.",
    stageLabel: "Needs review",
  },
  {
    id: "vendor-pitch",
    sender: "Leo Hart <leo@growthvector.ai>",
    subject: "Can we partner on outreach automation?",
    body:
      "We help software teams improve outbound performance and would love to explore a partnership. Let us know if you want to trade intros or co-market a workflow.",
    score: 2,
    isLead: false,
    status: "archived",
    reasoning:
      "The email is a partnership pitch rather than an inbound software buying inquiry.",
    reply:
      "Thanks for reaching out, Leo. At the moment we are focused on product evaluation inquiries, so we are not moving forward with partnership discussions from this inbox.",
    stageLabel: "Archived",
  },
];

const activity = [
  {
    title: "Reply draft prepared",
    body: "Northline Logistics was scored 9/10 and saved to Gmail drafts.",
    time: "2 min ago",
  },
  {
    title: "Manual review requested",
    body: "Acme Ops was kept in review because decision authority is still unclear.",
    time: "8 min ago",
  },
  {
    title: "Support request detected",
    body: "Helpdesk Support was classified as non-lead and held for review.",
    time: "14 min ago",
  },
];

const state = {
  selectedId: emails[0]?.id ?? null,
  filter: "all",
};

function getVisibleEmails() {
  if (state.filter === "lead") {
    return emails.filter((email) => email.isLead && email.status !== "archived");
  }

  if (state.filter === "review") {
    return emails.filter((email) => email.status === "review");
  }

  return emails;
}

function updateStats(root) {
  root.querySelector("[data-stat-unread]").textContent = String(
    emails.filter((email) => email.status !== "archived").length,
  );
  root.querySelector("[data-stat-leads]").textContent = String(
    emails.filter((email) => email.isLead).length,
  );
  root.querySelector("[data-stat-drafts]").textContent = String(
    emails.filter((email) => email.status === "draft").length,
  );
  root.querySelector("[data-stat-archived]").textContent = String(
    emails.filter((email) => email.status === "archived").length,
  );
}

function scoreClass(score) {
  if (score >= 8) return "score-pill";
  if (score >= 5) return "score-pill score-pill-muted";
  return "score-pill score-pill-muted";
}

function statusTag(email) {
  if (email.status === "archived") {
    return '<span class="tag tag-neutral">Archived</span>';
  }

  if (email.isLead && email.status === "draft") {
    return '<span class="tag tag-lead">Draft ready</span>';
  }

  return '<span class="tag tag-review">Manual review</span>';
}

function renderMailList(root) {
  const container = root.querySelector("[data-mail-list]");
  const visibleEmails = getVisibleEmails();

  if (!visibleEmails.some((email) => email.id === state.selectedId)) {
    state.selectedId = visibleEmails[0]?.id ?? null;
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
          <p class="mail-card-snippet">${email.body.slice(0, 118)}...</p>
          <div class="mail-card-tags">
            ${statusTag(email)}
            <span class="tag tag-neutral">${email.stageLabel}</span>
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
  const selected = emails.find((email) => email.id === state.selectedId);
  if (!selected) return;

  root.querySelector("[data-detail-subject]").textContent = selected.subject;
  root.querySelector("[data-detail-sender]").textContent = selected.sender;
  root.querySelector("[data-detail-score]").textContent = `${selected.score}/10`;
  root.querySelector("[data-detail-decision]").textContent = selected.isLead ? "Lead" : "Not a lead";
  root.querySelector("[data-detail-reasoning]").textContent = selected.reasoning;
  root.querySelector("[data-detail-body]").textContent = selected.body;

  const badge = root.querySelector("[data-detail-badge]");
  badge.textContent = selected.isLead ? "Lead" : "Review";
  badge.className = `badge ${selected.isLead ? "badge-success" : ""}`;

  const editor = root.querySelector("[data-reply-editor]");
  editor.value = selected.reply;

  root.querySelectorAll("[data-action]").forEach((button) => {
    button.onclick = () => {
      const action = button.getAttribute("data-action");
      if (action === "draft") {
        selected.status = "draft";
        selected.stageLabel = selected.isLead ? "Qualified lead" : "Reply drafted";
        selected.reply = editor.value;
        activity.unshift({
          title: "Draft saved",
          body: `${selected.sender.split("<")[0].trim()} reply was updated and marked ready for Gmail drafts.`,
          time: "Just now",
        });
      }

      if (action === "review") {
        selected.status = "review";
        selected.stageLabel = "Needs review";
        selected.reply = editor.value;
        activity.unshift({
          title: "Manual review requested",
          body: `${selected.sender.split("<")[0].trim()} was kept in the review queue for a human check.`,
          time: "Just now",
        });
      }

      if (action === "archive") {
        selected.status = "archived";
        selected.stageLabel = "Archived";
        activity.unshift({
          title: "Email archived",
          body: `${selected.sender.split("<")[0].trim()} was archived from the lead queue.`,
          time: "Just now",
        });
      }

      render(root);
    };
  });
}

function renderActivity(root) {
  const container = root.querySelector("[data-activity-list]");
  container.innerHTML = activity
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

function render(root) {
  updateStats(root);
  bindFilters(root);
  renderMailList(root);
  renderDetails(root);
  renderActivity(root);
}

const appRoot = document.querySelector("[data-workspace-app]");
if (appRoot) {
  render(appRoot);
}
