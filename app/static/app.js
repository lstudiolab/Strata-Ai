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


function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\\*\\*([^*\\n]+)\\*\\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\\*([^*\\n]+)\\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\\n]+)_/g, "<em>$1</em>");
  html = html.replace(/\\x60([^\\x60\\n]+)\\x60/g, '<span class="inline-code">$1</span>');
  return html;
}

function copyIconSvg() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="7" width="11" height="13" rx="2"></rect><path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
}

function renderMarkdown(value) {
  const source = String(value || "").replace(/\\r\\n/g, "\\n");
  const parts = source.split(/(\\x60{3,}[^\\n]*\\n?[\\s\\S]*?\\x60{3,})/g);
  const html = [];

  for (const part of parts) {
    if (!part) continue;

    const fence = part.match(/^\\x60{3,}([^\\n]*)\\n?([\\s\\S]*?)\\n?\\x60{3,}$/);
    if (fence) {
      const label = fence[1].trim() || "text";
      const content = fence[2].replace(/\\n$/, "");
      html.push(
        '<div class="copy-block">' +
          '<div class="copy-block-header">' +
            '<span class="copy-block-label">' + escapeHtml(label) + "</span>" +
            '<button class="copy-block-button" type="button" aria-label="Copy block">' +
              copyIconSvg() +
              "<span>Copy</span>" +
            "</button>" +
          "</div>" +
          '<pre class="copy-block-content"><code></code></pre>' +
        "</div>"
      );

      const block = html[html.length - 1];
      html[html.length - 1] = block.replace("<code></code>", "<code>" + escapeHtml(content) + "</code>");
      continue;
    }

    const lines = part.split("\\n");
    let inList = false;
    let listType = "";

    const closeList = () => {
      if (inList) {
        html.push(listType === "ol" ? "</ol>" : "</ul>");
        inList = false;
        listType = "";
      }
    };

    for (const line of lines) {
      const trimmed = line.trim();

      if (!trimmed) {
        closeList();
        html.push("<div class=\"markdown-spacer\"></div>");
        continue;
      }

      const unordered = trimmed.match(/^[-*+]\\s+(.+)$/);
      const ordered = trimmed.match(/^\\d+[.)]\\s+(.+)$/);

      if (unordered || ordered) {
        const type = ordered ? "ol" : "ul";
        if (!inList || listType !== type) {
          closeList();
          html.push(type === "ol" ? "<ol>" : "<ul>");
          inList = true;
          listType = type;
        }
        html.push("<li>" + renderInlineMarkdown((ordered || unordered)[1]) + "</li>");
        continue;
      }

      closeList();

      const heading = trimmed.match(/^(#{1,6})\\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length, 6);
        html.push("<h" + level + ">" + renderInlineMarkdown(heading[2]) + "</h" + level + ">");
        continue;
      }

      if (/^---+$/.test(trimmed) || /^___+$/.test(trimmed)) {
        html.push("<hr>");
        continue;
      }

      html.push("<p>" + renderInlineMarkdown(trimmed) + "</p>");
    }

    closeList();
  }

  return html.join("");
}

function renderAssistantMessage(element, value) {
  element.innerHTML = renderMarkdown(value);
  attachCopyButtons(element);
}

function attachCopyButtons(root) {
  root.querySelectorAll(".copy-block-button").forEach((button) => {
    if (button.dataset.copyReady === "true") return;
    button.dataset.copyReady = "true";

    button.addEventListener("click", async () => {
      const code = button.closest(".copy-block")?.querySelector(".copy-block-content code");
      const text = code ? code.textContent || "" : "";

      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        const fallback = document.createElement("textarea");
        fallback.value = text;
        fallback.setAttribute("readonly", "");
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.appendChild(fallback);
        fallback.select();
        document.execCommand("copy");
        fallback.remove();
      }

      const label = button.querySelector("span");
      if (label) label.textContent = "Copied";
      button.classList.add("copied");

      window.setTimeout(() => {
        if (label) label.textContent = "Copy";
        button.classList.remove("copied");
      }, 1400);
    });
  });
}
\nfunction addMessage(role, text, isStatus = false) {
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
