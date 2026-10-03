let isLoading = false;
let sessionId = null;
let currentModel = "default";

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const modelSelect = document.getElementById("modelSelect");

if (!sessionId) {
  sessionId = generateSessionId();
}

function generateSessionId() {
  return "session_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
}

function addMessage(role, text, isStatus = false) {
  const messageGroup = document.createElement("div");
  messageGroup.className = "message-group " + role;

  const message = document.createElement("div");
  message.className = "message " + role;
  if (isStatus) {
    message.classList.add("status");
  }
  message.textContent = text;

  messageGroup.appendChild(message);
  messagesContainer.appendChild(messageGroup);

  setTimeout(() => {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }, 0);
}

function updateLastStatus(text) {
  const statuses = messagesContainer.querySelectorAll(".message.status");
  if (statuses.length > 0) {
    statuses[statuses.length - 1].textContent = text;
  }
}

async function sendMessage() {
  if (isLoading) return;

  const message = messageInput.value.trim();
  if (!message) return;

  isLoading = true;
  messageInput.disabled = true;
  messageInput.value = "";
  sendButton.disabled = true;

  addMessage("user", message);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        model_type: currentModel
      })
    });

    if (!response.ok || !response.body) {
      addMessage("assistant", "Failed to connect to the AI server. Please try again.");
      resetInputState();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let hasStatus = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        if (!event.startsWith("data: ")) continue;

        const raw = event.replace(/^data:\s*/, "").trim();
        if (!raw) continue;

        try {
          const payload = JSON.parse(raw);

          if (payload.type === "status") {
            if (!hasStatus) {
              addMessage("assistant", payload.message, true);
              hasStatus = true;
            } else {
              updateLastStatus(payload.message);
            }
          } else if (payload.type === "answer") {
            const last = messagesContainer.lastChild;
            if (last && last.querySelector(".message.status")) {
              last.remove();
            }
            addMessage("assistant", payload.message);
          } else if (payload.type === "error") {
            addMessage("assistant", payload.message);
          }
        } catch (error) {
          console.error("Failed to parse response:", error);
        }
      }
    }
  } catch (error) {
    addMessage("assistant", "An error occurred. Please try again.");
    console.error("Send message error:", error);
  } finally {
    resetInputState();
  }
}

function resetInputState() {
  isLoading = false;
  messageInput.disabled = false;
  sendButton.disabled = false;
  messageInput.focus();
}

sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !isLoading) {
    e.preventDefault();
    sendMessage();
  }
});

modelSelect.addEventListener("change", function () {
  currentModel = this.value;
});

window.addEventListener("load", () => {
  addMessage("assistant", "Hi! I'm Strata AI. How can I help you today?");
});

messageInput.focus();
