let isLoading = false;
let sessionId = localStorage.getItem("strata_session_id");
let currentModel = "strata";

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatForm = document.getElementById("chatForm");
const modelSelect = document.getElementById("modelSelect");

const API_BASE =
  (window.STRATA_API_URL || document.documentElement.dataset.apiBase || "")
    .replace(/\/$/, "");

if (!sessionId) {
  sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 9);
  localStorage.setItem("strata_session_id", sessionId);
}

function scrollToActive(group, behavior = "smooth") {
  if (!group) return;

  requestAnimationFrame(() => {
    group.scrollIntoView({
      behavior,
      block: "start",
    });
  });
}

function scrollToBottom(behavior = "smooth") {
  requestAnimationFrame(() => {
    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior,
    });
  });
}

function addMessage(role, text, isStatus = false) {
  const group = document.createElement("div");
  group.className = "message-group " + role;

  const msg = document.createElement("div");
  msg.className = "message " + role;
  if (isStatus) msg.classList.add("status");
  msg.textContent = text;

  group.appendChild(msg);
  messagesContainer.appendChild(group);

  // New conversations are anchored to the current exchange rather than
  // leaving older messages in the main reading position.
  scrollToActive(group);

  return msg;
}

function updateLastStatus(text) {
  const statuses = messagesContainer.querySelectorAll(".message.status");
  if (statuses.length > 0) {
    statuses[statuses.length - 1].textContent = text;
  }
}

function removeLastStatus() {
  const statuses = messagesContainer.querySelectorAll(".message.status");
  if (!statuses.length) return;
  const statusMessage = statuses[statuses.length - 1];
  statusMessage.parentElement.remove();
}

async function loadModels() {
  try {
    const response = await fetch(API_BASE + "/api/models");
    if (!response.ok) return;

    const data = await response.json();
    if (!Array.isArray(data.models)) return;

    modelSelect.replaceChildren();
    for (const model of data.models) {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.name;
      modelSelect.appendChild(option);
    }

    modelSelect.value = currentModel;
    if (modelSelect.value !== currentModel && modelSelect.options.length) {
      currentModel = modelSelect.options[0].value;
      modelSelect.value = currentModel;
    }
  } catch (error) {
    console.warn("Could not load models:", error);
  }
}

async function sendMessage() {
  if (isLoading) return;

  const message = messageInput.value.trim();
  if (!message) return;

  isLoading = true;
  messageInput.disabled = true;
  sendButton.disabled = true;
  messageInput.value = "";

  const userMessage = addMessage("user", message);

  // Put the active exchange at the reading position. Older messages remain
  // in the conversation history, but are naturally pushed above the viewport.
  scrollToActive(userMessage.parentElement);

  let assistantMessage = null;
  let assistantGroup = null;
  let fullAnswer = "";

  try {
    const response = await fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        model_type: currentModel,
      }),
    });

    if (!response.ok) {
      let errorText = "Failed to connect to the AI server.";
      try {
        const errorData = await response.json();
        if (errorData.error) errorText = errorData.error;
      } catch (_) {
        // Keep the generic error when the server did not return JSON.
      }
      addMessage("assistant", errorText, false);
      return;
    }

    if (!response.body) {
      addMessage("assistant", "The AI server returned an empty response.");
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const processEvent = (event) => {
      const dataLine = event
        .split("\n")
        .find((line) => line.startsWith("data:"));

      if (!dataLine) return;

      const raw = dataLine.replace(/^data:\s?/, "").trim();
      if (!raw) return;

      try {
        const payload = JSON.parse(raw);

        if (payload.type === "status") {
          const existingStatus = messagesContainer.querySelector(".message.status");
          if (existingStatus) {
            updateLastStatus(payload.message);
          } else {
            addMessage("assistant", payload.message || "Thinking...", true);
          }
        } else if (payload.type === "delta") {
          removeLastStatus();
          fullAnswer += payload.message || "";

          if (!assistantMessage) {
            assistantMessage = addMessage("assistant", "");
            assistantGroup = assistantMessage.parentElement;
          }

          assistantMessage.textContent = fullAnswer;

          // Keep the live answer in view while it streams without snapping
          // the whole conversation back to the very bottom.
          scrollToActive(assistantGroup, "auto");
        } else if (payload.type === "answer") {
          removeLastStatus();

          if (!assistantMessage) {
            assistantMessage = addMessage("assistant", payload.message || "");
            assistantGroup = assistantMessage.parentElement;
          } else {
            assistantMessage.textContent = payload.message || fullAnswer;
          }

          scrollToActive(assistantGroup, "smooth");
        } else if (payload.type === "error") {
          removeLastStatus();
          addMessage("assistant", payload.message || "The AI request failed.");
        }
      } catch (error) {
        console.warn("SSE parse error:", error);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        processEvent(event);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) processEvent(buffer);
  } catch (error) {
    console.error("Chat request failed:", error);
    removeLastStatus();
    addMessage("assistant", "An error occurred while contacting Strata.");
  } finally {
    resetInput();
  }
}

function resetInput() {
  isLoading = false;
  messageInput.disabled = false;
  sendButton.disabled = false;
  messageInput.focus();
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage();
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !isLoading) {
    event.preventDefault();
    sendMessage();
  }
});

modelSelect.addEventListener("change", (event) => {
  currentModel = event.target.value;
});

window.addEventListener("load", async () => {
  await loadModels();
  addMessage("assistant", "Hi! I'm Strata AI. How can I help you today?");
});
