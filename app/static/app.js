let isLoading = false;
let sessionId = localStorage.getItem("strata_session_id");

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatForm = document.getElementById("chatForm");
const contextButton = document.getElementById("contextButton");
const contextPanel = document.getElementById("contextPanel");
const contextInput = document.getElementById("contextInput");
const contextClose = document.getElementById("contextClose");

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

function addMessage(role, text, isStatus = false) {
  const group = document.createElement("div");
  group.className = "message-group " + role;

  const msg = document.createElement("div");
  msg.className = "message " + role;
  if (isStatus) msg.classList.add("status");
  msg.textContent = text;

  group.appendChild(msg);
  messagesContainer.appendChild(group);
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
  statuses[statuses.length - 1].parentElement.remove();
}

async function sendMessage() {
  if (isLoading) return;

  const message = messageInput.value.trim();
  const contextText = contextInput ? contextInput.value.trim() : "";
  if (!message) return;

  isLoading = true;
  messageInput.disabled = true;
  sendButton.disabled = true;
  messageInput.value = "";

  const userMessage = addMessage("user", message);
  scrollToActive(userMessage.parentElement);

  let assistantMessage = null;
  let assistantGroup = null;
  let fullAnswer = "";

  try {
    const response = await fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        model_type: "strata",
        pasted_text: contextText,
      }),
    });

    if (!response.ok) {
      let errorText = "Failed to connect to the AI server.";
      try {
        const errorData = await response.json();
        if (errorData.error) errorText = errorData.error;
      } catch (_) {}
      addMessage("assistant", errorText);
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

function toggleContextPanel() {
  if (!contextPanel) return;
  contextPanel.hidden = !contextPanel.hidden;
  if (!contextPanel.hidden) {
    contextInput.focus();
  } else {
    messageInput.focus();
  }
}

contextButton.addEventListener("click", async () => {
  if (!contextPanel.hidden) {
    toggleContextPanel();
    return;
  }

  contextPanel.hidden = false;
  contextInput.focus();

  if (!contextInput.value && navigator.clipboard && navigator.clipboard.readText) {
    try {
      const clipboardText = await navigator.clipboard.readText();
      if (clipboardText.trim()) {
        contextInput.value = clipboardText;
      }
    } catch (_) {
      // The user can paste normally when clipboard permission is unavailable.
    }
  }
});

contextClose.addEventListener("click", toggleContextPanel);

contextInput.addEventListener("input", () => {
  const count = contextInput.value.length;
  contextButton.setAttribute(
    "aria-label",
    count ? "Text attached" : "Add text"
  );
});

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

window.addEventListener("load", () => {
  addMessage("assistant", "Hi! I'm Strata AI. How can I help you today?");
});
