const statusLabels = {
  never: "Nunca executada",
  running: "Em execução",
  success: "Sucesso",
  error: "Erro",
};

let pollingTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-action='run']").forEach((button) => {
    button.addEventListener("click", handleRunClick);
  });

  updateStatusBadges();

  if (hasRunningAutomation()) {
    startPolling();
  }
});

async function handleRunClick(event) {
  const card = event.currentTarget.closest("[data-automation-id]");
  const automationId = card.dataset.automationId;

  setCardRunning(card);
  clearPageMessage();

  try {
    const response = await fetch(`/api/automations/${automationId}/run`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });
    const payload = await response.json();

    if (!response.ok) {
      showPageMessage(payload.error || "Não foi possível iniciar a automação.", true);
      await refreshAutomations();
      return;
    }

    showPageMessage(payload.message || "Automação iniciada.", false);
    startPolling();
  } catch (error) {
    showPageMessage("Falha de comunicação com o servidor.", true);
    await refreshAutomations();
  }
}

async function refreshAutomations() {
  try {
    const response = await fetch("/api/automations", {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      showPageMessage("Não foi possível atualizar o status das automações.", true);
      return;
    }

    const payload = await response.json();
    payload.automations.forEach(updateCard);

    if (payload.automations.some((automation) => automation.is_running)) {
      startPolling();
    } else {
      stopPolling();
    }
  } catch (error) {
    showPageMessage("Falha ao consultar o status das automações.", true);
  }
}

function updateCard(automation) {
  const card = document.querySelector(`[data-automation-id="${automation.id}"]`);
  if (!card) {
    return;
  }

  setText(card, "last-started-at", formatDateTime(automation.last_started_at));
  setText(card, "duration", automation.duration_label);
  setText(card, "status-label", statusLabels[automation.status] || automation.status);

  const badge = card.querySelector("[data-field='status']");
  badge.dataset.status = automation.status;
  badge.textContent = statusLabels[automation.status] || automation.status;

  const errorBox = card.querySelector("[data-field='error-message']");
  if (automation.status === "error" && automation.error_message) {
    errorBox.textContent = automation.error_message;
    errorBox.classList.remove("hidden");
  } else {
    errorBox.textContent = "";
    errorBox.classList.add("hidden");
  }

  updateLogs(card, automation.execution_logs || [], automation.is_running);

  const button = card.querySelector("[data-action='run']");
  const buttonLabel = card.querySelector("[data-field='button-label']");
  const spinner = card.querySelector(".loading-spinner");

  button.disabled = automation.is_running;
  buttonLabel.textContent = automation.is_running ? "Executando..." : "Executar automação";
  spinner.classList.toggle("hidden", !automation.is_running);

  updateStatusBadges();
}

function setCardRunning(card) {
  const button = card.querySelector("[data-action='run']");
  const buttonLabel = card.querySelector("[data-field='button-label']");
  const spinner = card.querySelector(".loading-spinner");
  const badge = card.querySelector("[data-field='status']");

  button.disabled = true;
  buttonLabel.textContent = "Executando...";
  spinner.classList.remove("hidden");
  badge.dataset.status = "running";
  badge.textContent = statusLabels.running;
  setText(card, "status-label", statusLabels.running);
  updateLogs(card, [], true);
  updateStatusBadges();
}

function updateLogs(card, logs, isRunning) {
  const logsSection = card.querySelector("[data-field='logs-section']");
  const logsElement = card.querySelector("[data-field='execution-logs']");
  if (!logsSection || !logsElement) {
    return;
  }

  if (logs.length === 0 && !isRunning) {
    logsElement.textContent = "";
    logsSection.classList.add("hidden");
    return;
  }

  logsElement.textContent = logs.join("\n");
  logsSection.classList.remove("hidden");
  logsElement.scrollTop = logsElement.scrollHeight;
}

function setText(card, field, value) {
  const element = card.querySelector(`[data-field='${field}']`);
  element.textContent = value || "Nunca";
}

function formatDateTime(value) {
  if (!value) {
    return "Nunca";
  }

  const date = new Date(value);
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
}

function startPolling() {
  if (pollingTimer) {
    return;
  }

  pollingTimer = window.setInterval(refreshAutomations, 2000);
}

function stopPolling() {
  if (!pollingTimer) {
    return;
  }

  window.clearInterval(pollingTimer);
  pollingTimer = null;
}

function hasRunningAutomation() {
  return Array.from(document.querySelectorAll("[data-field='status']")).some(
    (badge) => badge.dataset.status === "running",
  );
}

function updateStatusBadges() {
  document.querySelectorAll("[data-field='status']").forEach((badge) => {
    badge.classList.remove("status-never", "status-running", "status-success", "status-error");
    badge.classList.add(`status-${badge.dataset.status || "never"}`);
  });
}

function showPageMessage(message, isError) {
  const pageMessage = document.getElementById("page-message");
  pageMessage.textContent = message;
  pageMessage.classList.remove(
    "hidden",
    "border-red-400/40",
    "bg-red-500/10",
    "text-red-100",
    "border-emerald-400/40",
    "bg-emerald-500/10",
    "text-emerald-100",
  );

  pageMessage.classList.add(
    isError ? "border-red-400/40" : "border-emerald-400/40",
    isError ? "bg-red-500/10" : "bg-emerald-500/10",
    isError ? "text-red-100" : "text-emerald-100",
  );
}

function clearPageMessage() {
  const pageMessage = document.getElementById("page-message");
  pageMessage.textContent = "";
  pageMessage.classList.add("hidden");
}
