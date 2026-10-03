let isLoading = false;
let sessionId = null;
let currentModel = "default";

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const modelSelect = document.getElementById("modelSelect");

if (!sessionId) {
  sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 9);
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
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
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
  sendButton.disabled = true;
  messageInput.value = "";

  addMessage("user", message);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        model_type: currentModel,
      }),
    });

    if (!response.ok || !response.body) {
      addMessage("assistant", "Failed to connect to the AI server.");
      resetInput();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let statusShown = false;

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
            if (!statusShown) {
              addMessage("assistant", payload.message, true);
              statusShown = true;
            } else {
              updateLastStatus(payload.message);
            }
          } else if (payload.type === "answer") {
            const lastGroup = messagesContainer.lastElementChild;
            if (lastGroup && lastGroup.querySelector(".message.status")) {
              lastGroup.remove();
            }
            addMessage("assistant", payload.message);
          } else if (payload.type === "error") {
            addMessage("assistant", payload.message, false);
          }
        } catch (err) {
          console.error("Parse error:", err);
        }
      }
    }
  } catch (err) {
    addMessage("assistant", "An error occurred while contacting the AI.");
    console.error(err);
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

sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !isLoading) {
    event.preventDefault();
    sendMessage();
  }
});

modelSelect.addEventListener("change", (event) => {
  currentModel = event.target.value;
});

window.addEventListener("load", () => {
  addMessage("assistant", "Hi! I'm Strata AI. How can I help you today?");
});
