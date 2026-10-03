let isLoading = false;
let sessionId = null;

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");

// Generate session ID on page load
if (!sessionId) {
  sessionId = generateSessionId();
}

function generateSessionId() {
  return "session_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
}

// Add message to chat
function addMessage(role, text, isStatus) {
  if (isStatus === undefined) isStatus = false;
  
  const messageGroup = document.createElement("div");
  messageGroup.className = "message-group " + role;

  const message = document.createElement("div");
  message.className = "message " + role;
  if (isStatus) message.classList.add("status");

  if (isStatus) {
    // Extract emoji from status message if present
    const emojiPattern = /^([\ud83d\udd0d\ud83c\udf10\ud83d\udcda\u2699\ufe0f\u2705])\s+(.*)/;
    const emojiMatch = text.match(emojiPattern);
    if (emojiMatch) {
      message.innerHTML = '<span class="status-indicator">' + emojiMatch[1] + '</span>' + escapeHtml(emojiMatch[2]);
    } else {
      message.textContent = text;
    }
  } else {
    message.textContent = text;
  }

  messageGroup.appendChild(message);
  messagesContainer.appendChild(messageGroup);

  // Scroll to bottom
  setTimeout(function() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }, 0);
}

function addErrorMessage(text) {
  const messageGroup = document.createElement("div");
  messageGroup.className = "message-group assistant";

  const message = document.createElement("div");
  message.className = "message error";
  message.textContent = text;

  messageGroup.appendChild(message);
  messagesContainer.appendChild(messageGroup);

  setTimeout(function() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }, 0);
}

function escapeHtml(text) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  };
  return text.replace(/[&<>"']/g, function(m) {
    return map[m];
  });
}

async function sendMessage() {
  if (isLoading) return; // Prevent sending while waiting for response

  const message = messageInput.value.trim();
  if (!message) return;

  // Disable input and show loading state
  isLoading = true;
  messageInput.disabled = true;
  messageInput.value = "";
  sendButton.disabled = true;

  // Add user message to chat
  addMessage("user", message);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message, session_id: sessionId })
    });

    if (!response.ok || !response.body) {
      addErrorMessage("Failed to connect to the AI server. Please try again.");
      isLoading = false;
      messageInput.disabled = false;
      sendButton.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const result = await reader.read();
      const value = result.value;
      const done = result.done;
      
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (let i = 0; i < events.length; i++) {
        const event = events[i];
        if (!event.startsWith("data: ")) continue;
        const raw = event.replace(/^data:\s*/, "").trim();
        if (!raw) continue;

        try {
          const payload = JSON.parse(raw);

          if (payload.type === "status") {
            addMessage("assistant", payload.message, true);
          } else if (payload.type === "answer") {
            // Remove last status message if it exists and add the full response
            const lastMessage = messagesContainer.lastChild;
            if (lastMessage && lastMessage.querySelector(".message.status")) {
              lastMessage.remove();
            }
            addMessage("assistant", payload.message);
          } else if (payload.type === "error") {
            addErrorMessage(payload.message);
          }
        } catch (error) {
          console.error("Failed to parse response:", error);
        }
      }
    }
  } catch (error) {
    addErrorMessage("An error occurred. Please try again.");
    console.error("Send message error:", error);
  } finally {
    // Re-enable input
    isLoading = false;
    messageInput.disabled = false;
    sendButton.disabled = false;
    messageInput.focus();
  }
}

// Event listeners
sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && !e.shiftKey && !isLoading) {
    e.preventDefault();
    sendMessage();
  }
});

// Focus input on load
messageInput.focus();

// Show welcome message
window.addEventListener("load", function() {
  addMessage("assistant", "Hi! I'm Strata AI. I can help you with coding, research, writing, analysis, and much more. What can I help you with today?");
});
