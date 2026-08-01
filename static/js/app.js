const statusLabels = {
  never: "Nunca executada",
  running: "Em execução",
  success: "Sucesso",
  error: "Erro",
};

let pollingTimer = null;
let driveUploadSubmitting = false;
let activeDriveCard = null;

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-action='run']").forEach((button) => {
    button.addEventListener("click", handleRunClick);
  });

  setupDriveUploadModal();
  updateStatusBadges();

  if (hasRunningAutomation()) {
    startPolling();
  }
});

async function handleRunClick(event) {
  const card = event.currentTarget.closest("[data-automation-id]");
  const automationId = card.dataset.automationId;

  if (card.dataset.requiresFile === "true") {
    openDriveUploadModal(card);
    return;
  }

  setCardRunning(card);
  clearPageMessage();

  try {
    const response = await authenticatedFetch(`/api/automations/${automationId}/run`, {
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

function setupDriveUploadModal() {
  const modal = getDriveModal();
  if (!modal) {
    return;
  }

  document.getElementById("drive-upload-input").addEventListener("change", handleDriveFileChange);
  document.getElementById("drive-upload-submit").addEventListener("click", submitDriveUpload);

  modal.querySelectorAll("[data-action='close-drive-modal']").forEach((button) => {
    button.addEventListener("click", closeDriveUploadModal);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeDriveUploadModal();
    }
  });
}

function openDriveUploadModal(card) {
  activeDriveCard = card;
  clearDriveUploadError();
  resetDriveUploadForm();

  const modal = getDriveModal();
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  document.getElementById("drive-upload-input").focus();
}

function closeDriveUploadModal() {
  if (driveUploadSubmitting) {
    return;
  }

  const modal = getDriveModal();
  modal.classList.add("hidden");
  modal.classList.remove("flex");
  resetDriveUploadForm();
  activeDriveCard = null;
}

function handleDriveFileChange() {
  const input = document.getElementById("drive-upload-input");
  const filename = document.getElementById("drive-upload-filename");
  const submitButton = document.getElementById("drive-upload-submit");
  const file = input.files[0];

  clearDriveUploadError();

  if (!file) {
    filename.textContent = "";
    submitButton.disabled = true;
    return;
  }

  filename.textContent = file.name;
  if (!isAllowedXlsxName(file.name)) {
    showDriveUploadError("Formato inválido. Envie somente arquivos .xlsx.");
    submitButton.disabled = true;
    return;
  }

  submitButton.disabled = false;
}

async function submitDriveUpload() {
  if (driveUploadSubmitting) {
    return;
  }

  const input = document.getElementById("drive-upload-input");
  const file = input.files[0];
  if (!file || !isAllowedXlsxName(file.name)) {
    showDriveUploadError("Selecione um arquivo .xlsx para executar a automação.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  setDriveUploadSubmitting(true);
  clearDriveUploadError();
  clearPageMessage();

  try {
    const response = await authenticatedFetch("/api/automations/drive-update/run", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok) {
      showDriveUploadError(payload.error || "Não foi possível iniciar a automação.");
      await refreshAutomations();
      return;
    }

    if (payload.automation) {
      updateCard(payload.automation);
    } else if (activeDriveCard) {
      setCardRunning(activeDriveCard);
    }

    showPageMessage(payload.message || "Automação iniciada.", false);
    setDriveUploadSubmitting(false);
    closeDriveUploadModal();
    startPolling();
  } catch (error) {
    showDriveUploadError("Falha de comunicação com o servidor.");
  } finally {
    if (driveUploadSubmitting) {
      setDriveUploadSubmitting(false, { keepError: true });
    }
  }
}

function setDriveUploadSubmitting(isSubmitting, options = {}) {
  driveUploadSubmitting = isSubmitting;
  document.getElementById("drive-upload-submit").disabled = isSubmitting;
  document.getElementById("drive-upload-input").disabled = isSubmitting;
  document.getElementById("drive-upload-submit-label").textContent = isSubmitting
    ? "Enviando..."
    : "Executar";
  document.getElementById("drive-upload-spinner").classList.toggle("hidden", !isSubmitting);
  getDriveModal().querySelectorAll("[data-action='close-drive-modal']").forEach((button) => {
    button.disabled = isSubmitting;
  });

  if (!isSubmitting && !options.keepError) {
    handleDriveFileChange();
  }
}

function isAllowedXlsxName(filename) {
  const normalizedName = filename.toLowerCase();
  return normalizedName.endsWith(".xlsx") && normalizedName.split(".").length === 2;
}

function resetDriveUploadForm() {
  const input = document.getElementById("drive-upload-input");
  input.value = "";
  input.disabled = false;
  document.getElementById("drive-upload-filename").textContent = "";
  document.getElementById("drive-upload-submit").disabled = true;
  document.getElementById("drive-upload-submit-label").textContent = "Executar";
  document.getElementById("drive-upload-spinner").classList.add("hidden");
  getDriveModal().querySelectorAll("[data-action='close-drive-modal']").forEach((button) => {
    button.disabled = false;
  });
  clearDriveUploadError();
}

function showDriveUploadError(message) {
  const errorBox = document.getElementById("drive-upload-error");
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearDriveUploadError() {
  const errorBox = document.getElementById("drive-upload-error");
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function getDriveModal() {
  return document.getElementById("drive-upload-modal");
}

async function refreshAutomations() {
  try {
    const response = await authenticatedFetch("/api/automations", {
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

async function authenticatedFetch(url, options = {}) {
  const fetchOptions = {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  };

  if ((fetchOptions.method || "GET").toUpperCase() === "POST") {
    fetchOptions.headers["X-CSRF-Token"] = getCsrfToken();
  }

  const response = await fetch(url, fetchOptions);
  if (response.status === 401) {
    window.location.href = "/login";
  }
  return response;
}

function getCsrfToken() {
  const token = document.querySelector("meta[name='csrf-token']");
  return token ? token.getAttribute("content") : "";
}
