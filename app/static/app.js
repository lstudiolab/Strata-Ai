let isLoading = false;
let sessionId = localStorage.getItem("strata_session_id");

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatForm = document.getElementById("chatForm");
const attachmentButton = document.getElementById("attachmentButton");
const fileInput = document.getElementById("fileInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const tokenMeterButton = document.getElementById("tokenMeterButton");
const tokenMeterPercent = document.getElementById("tokenMeterPercent");
const tokenMeterFill = document.getElementById("tokenMeterFill");
const settingsButton = document.getElementById("settingsButton");
const settingsPanel = document.getElementById("settingsPanel");
const settingsClose = document.getElementById("settingsClose");
const conversationDrawer = document.getElementById("conversationDrawer");
const conversationList = document.getElementById("conversationList");
const conversationClose = document.getElementById("conversationClose");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const newConversationButton = document.getElementById("newConversationButton");

let selectedAttachment = null;
let selectedAttachmentData = "";

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
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");
  html = html.replace(/\x60([^\x60\n]+)\x60/g, '<span class="inline-code">$1</span>');
  return html;
}

function copyIconSvg() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="7" width="11" height="13" rx="2"></rect><path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
}

function renderMarkdown(value) {
  const source = String(value || "").replace(/\r\n/g, "\n");
  const parts = source.split(/(\x60{3,}[^\n]*\n?[\s\S]*?\x60{3,})/g);
  const html = [];

  for (const part of parts) {
    if (!part) continue;

    const fence = part.match(/^\x60{3,}([^\n]*)\n?([\s\S]*?)\n?\x60{3,}$/);
    if (fence) {
      const label = fence[1].trim() || "text";
      const content = fence[2].replace(/\n$/, "");
      html.push(
        '<div class="copy-block">' +
          '<div class="copy-block-header">' +
            '<span class="copy-block-label">' + escapeHtml(label) + "</span>" +
            '<button class="copy-block-button" type="button" aria-label="Copy block">' +
              copyIconSvg() +
              "<span>Copy</span>" +
            "</button>" +
          "</div>" +
          '<pre class="copy-block-content"><code>' + escapeHtml(content) + "</code></pre>" +
        "</div>"
      );
      continue;
    }

    const lines = part.split("\n");
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

      const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);

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

      const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
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
      const block = button.closest(".copy-block");
      const code = block ? block.querySelector(".copy-block-content code") : null;
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

function addResponseActions(group, msg) {
  if (!group || !msg || group.querySelector(".response-actions")) return;

  const actions = document.createElement("div");
  actions.className = "response-actions response-actions-enter";

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "response-action";
  copyButton.setAttribute("aria-label", "Copy response");
  copyButton.innerHTML = copyIconSvg() + "<span>Copy</span>";
  copyButton.addEventListener("click", async () => {
    const text = msg.textContent || "";
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
    const label = copyButton.querySelector("span");
    if (label) label.textContent = "Copied";
    copyButton.classList.add("copied");
    window.setTimeout(() => {
      if (label) label.textContent = "Copy";
      copyButton.classList.remove("copied");
    }, 1400);
  });

  const ttsButton = document.createElement("button");
  ttsButton.type = "button";
  ttsButton.className = "response-action tts-button";
  ttsButton.setAttribute("aria-label", "Read response aloud");
  ttsButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Z"></path><path d="M16 9.5c1.2 1.2 1.2 3.8 0 5"></path><path d="M18.5 7c2.6 2.7 2.6 7.3 0 10"></path></svg><span>Listen</span>';
  ttsButton.addEventListener("click", () => {
    if (!("speechSynthesis" in window)) return;
    if (speechSynthesis.speaking) {
      speechSynthesis.cancel();
      ttsButton.classList.remove("speaking");
      const label = ttsButton.querySelector("span");
      if (label) label.textContent = "Listen";
      return;
    }
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(msg.textContent || "");
    utterance.rate = 0.98;
    utterance.pitch = 1;
    ttsButton.classList.add("speaking");
    const label = ttsButton.querySelector("span");
    if (label) label.textContent = "Stop";
    utterance.onend = () => {
      ttsButton.classList.remove("speaking");
      if (label) label.textContent = "Listen";
    };
    utterance.onerror = () => {
      ttsButton.classList.remove("speaking");
      if (label) label.textContent = "Listen";
    };
    speechSynthesis.speak(utterance);
  });

  actions.append(copyButton, ttsButton);
  group.appendChild(actions);
}

function addMessage(role, text, isStatus = false, attachment = null, completed = false) {
  const group = document.createElement("div");
  group.className = "message-group " + role;

  const msg = document.createElement("div");
  msg.className = "message " + role;
  if (isStatus) msg.classList.add("status");
  if (role !== "assistant" || isStatus) {
    msg.textContent = text || "";
  }

  if (role === "user" && attachment?.data?.startsWith("data:image/")) {
    const image = document.createElement("img");
    image.className = "message-attachment-image";
    image.src = attachment.data;
    image.alt = attachment.name || "Attached image";
    image.loading = "lazy";
    msg.appendChild(image);
  }

  group.appendChild(msg);

  if (role === "assistant" && !isStatus && completed) {
    addResponseActions(group, msg);
  }

  messagesContainer.appendChild(group);
  group.classList.add("message-enter");
  if (role === "user" && !isStatus) group.classList.add("message-sent");
  if (role === "assistant" && isStatus) group.classList.add("generating");
  scrollToActive(group);

  return msg;
}

function updateLastStatus(text) {
  const statuses = messagesContainer.querySelectorAll(".message.status");
  if (statuses.length > 0) {
    statuses[statuses.length - 1].textContent = text;
    statuses[statuses.length - 1].parentElement.classList.add("generating");
  }
}

function removeLastStatus() {
  const statuses = messagesContainer.querySelectorAll(".message.status");
  if (!statuses.length) return;
  statuses[statuses.length - 1].parentElement.remove();
}

async function stopGeneration() {
  if (!isLoading) return;
  try {
    if (window.__strataAbortController) {
      window.__strataAbortController.abort();
    }
  } catch (_) {}
  isLoading = false;
  messageInput.disabled = false;
  sendButton.disabled = false;
  sendButton.classList.remove("stop-generating");
  sendButton.setAttribute("aria-label", "Send message");
  sendButton.title = "Send message";
  removeLastStatus();
  document.querySelectorAll(".message-group.generating").forEach((group) => {
    group.classList.remove("generating");
  });
  messageInput.focus();
}

async function sendMessage() {
  if (isLoading) return;
  const message = messageInput.value.trim();
  const contextText = "";
  if (!message && !selectedAttachmentData) return;

  isLoading = true;
  messageInput.disabled = true;
  sendButton.disabled = false;
  sendButton.classList.add("stop-generating");
  sendButton.setAttribute("aria-label", "Stop generating message");
  sendButton.title = "Stop generating";
  messageInput.value = "";
  messageInput.blur();

  const displayMessage = message || (selectedAttachment?.name ? "Attached: " + selectedAttachment.name : "Image");
  const sentAttachment = selectedAttachment && selectedAttachment.type.startsWith("image/")
    ? { data: selectedAttachmentData, name: selectedAttachment.name }
    : null;
  const userMessage = addMessage("user", displayMessage, false, sentAttachment);
  scrollToActive(userMessage.parentElement);

  let assistantMessage = null;
  let assistantGroup = null;
  let fullAnswer = "";
  addMessage("assistant", "Thinking", true);
  const abortController = new AbortController();
  window.__strataAbortController = abortController;

  try {
    const response = await fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      signal: abortController.signal,
      body: JSON.stringify({
        message,
        session_id: sessionId,
        model_type: "strata",
        pasted_text: contextText,
        image_data: selectedAttachmentData,
        attachment_name: selectedAttachment?.name || "",
        attachment_type: selectedAttachment?.type || "",
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
      const dataLines = event
        .replace(/\r/g, "")
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^\s?/, ""));

      if (!dataLines.length) return;

      const raw = dataLines.join("\n").trim();
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
          return;
        }

        if (payload.type === "delta") {
          removeLastStatus();
          fullAnswer += String(payload.message || "");

          if (!assistantMessage) {
            assistantMessage = addMessage("assistant", "");
            assistantGroup = assistantMessage.parentElement;
          }

          renderAssistantMessage(assistantMessage, fullAnswer);
          scrollToActive(assistantGroup, "auto");
          return;
        }

        if (payload.type === "answer") {
          removeLastStatus();
          const finalAnswer = String(payload.message || fullAnswer || "");

          if (!assistantMessage) {
            assistantMessage = addMessage("assistant", finalAnswer);
            assistantGroup = assistantMessage.parentElement;
          } else {
            fullAnswer = finalAnswer;
            renderAssistantMessage(assistantMessage, finalAnswer);
          }

          const completedText = finalAnswer || "I couldn't generate a response. Please try again.";
          renderAssistantMessage(assistantMessage, completedText);
          assistantGroup.classList.remove("generating");
          addResponseActions(assistantGroup, assistantMessage);
          assistantGroup.classList.add("message-complete");

          scrollToActive(assistantGroup, "smooth");
          return;
        }

        if (payload.type === "error") {
          removeLastStatus();
          if (!assistantMessage) {
            addMessage("assistant", payload.message || "The AI request failed.");
          } else {
            renderAssistantMessage(
              assistantMessage,
              payload.message || "The AI request failed."
            );
          }
        }
      } catch (error) {
        console.warn("SSE parse error:", error, raw.slice(0, 300));
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

    // The server's final answer event is authoritative. If a proxy/client
    // dropped a final SSE boundary but the stream still contained answer text,
    // make sure the user never ends up with a missing assistant message.
    if (!assistantMessage && fullAnswer.trim()) {
      assistantMessage = addMessage("assistant", fullAnswer);
      assistantGroup = assistantMessage.parentElement;
      assistantGroup.classList.remove("generating");
      addResponseActions(assistantGroup, assistantMessage);
      assistantGroup.classList.add("message-complete");
    } else if (assistantMessage && fullAnswer.trim()) {
      assistantGroup.classList.remove("generating");
      renderAssistantMessage(assistantMessage, fullAnswer);
      addResponseActions(assistantGroup, assistantMessage);
      assistantGroup.classList.add("message-complete");
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      console.log("Strata generation stopped by user.");
    } else {
      console.error("Chat request failed:", error);
      removeLastStatus();
      document.querySelectorAll(".message-group.generating").forEach((group) => {
        group.classList.remove("generating");
      });
      addMessage("assistant", "An error occurred while contacting Strata.");
    }
  } finally {
    if (window.__strataAbortController === abortController) {
      window.__strataAbortController = null;
    }
    resetInput();
    clearAttachment();
  }
}


function closeSettings() {
  if (!settingsPanel) return;
  settingsPanel.classList.remove("open");
  settingsPanel.setAttribute("aria-hidden", "true");
}

function openSettings() {
  if (!settingsPanel) return;
  settingsPanel.classList.add("open");
  settingsPanel.setAttribute("aria-hidden", "false");
}

async function refreshTokenMeter() {
  if (!tokenMeterPercent || !tokenMeterFill) return;
  try {
    const response = await fetch("/api/credits", { cache: "no-store" });
    const data = await response.json();
    const bucket = data?.tokens || {};
    const remaining = Number(bucket.remaining);
    const limit = Number(bucket.limit);
    const percent = Number(bucket.remaining_percent);
    if (!Number.isFinite(remaining) || !Number.isFinite(limit) || limit <= 0) {
      tokenMeterPercent.textContent = "—";
      tokenMeterFill.style.setProperty("--meter-progress", "0deg");
      tokenMeterButton?.setAttribute("title", "Token usage will appear after Strata contacts the API");
      return;
    }
    const safePercent = Math.max(0, Math.min(100, percent));
    tokenMeterPercent.textContent = safePercent >= 10 ? Math.round(safePercent) + "%" : safePercent.toFixed(1) + "%";
    tokenMeterFill.style.setProperty("--meter-progress", (safePercent * 3.6) + "deg");
    tokenMeterButton?.setAttribute("title", Math.round(remaining).toLocaleString() + " tokens remaining in the current rate-limit window");
  } catch {
    tokenMeterPercent.textContent = "—";
  }
}

if (tokenMeterButton) {
  tokenMeterButton.addEventListener("click", refreshTokenMeter);
}
refreshTokenMeter();
setInterval(refreshTokenMeter, 15000);

function closeConversationDrawer() {
  closeSettings();
}

function openConversationDrawer() {
  openSettings();
  loadConversations();
}

function startNewConversation() {
  sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 9);
  localStorage.setItem("strata_session_id", sessionId);
  messagesContainer.innerHTML = "";
  clearAttachment();
  closeConversationDrawer();
}

async function loadConversations() {
  if (!conversationList) return;
  conversationList.innerHTML = "Loading conversations...";
  try {
    const response = await fetch(API_BASE + "/api/conversations");
    const data = await response.json();
    const conversations = Array.isArray(data.conversations) ? data.conversations : [];
    conversationList.innerHTML = "";
    if (!conversations.length) {
      conversationList.textContent = "No conversations yet.";
      return;
    }
    conversations.forEach((conversation) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "conversation-item" + (conversation.id === sessionId ? " active" : "");
      const title = document.createElement("span");
      title.className = "conversation-title";
      title.textContent = conversation.title || "New conversation";
      const meta = document.createElement("span");
      meta.className = "conversation-meta";
      meta.textContent = (conversation.message_count || 0) + " messages";
      button.append(title, meta);
      button.addEventListener("click", () => loadConversation(conversation.id));
      conversationList.appendChild(button);
    });
  } catch (_) {
    conversationList.textContent = "Unable to load conversations.";
  }
}

async function loadConversation(id) {
  try {
    const response = await fetch(API_BASE + "/api/conversations/" + encodeURIComponent(id));
    if (!response.ok) throw new Error("load failed");
    const data = await response.json();
    sessionId = id;
    localStorage.setItem("strata_session_id", sessionId);
    messagesContainer.innerHTML = "";
    for (const item of data.messages || []) {
      addMessage(item.role === "user" ? "user" : "assistant", item.content || "");
    }
    closeConversationDrawer();
  } catch (_) {
    addMessage("assistant", "I couldn't load that conversation.");
  }
}

function resetInput() {
  isLoading = false;
  messageInput.disabled = false;
  sendButton.disabled = false;
  sendButton.classList.remove("stop-generating");
  sendButton.setAttribute("aria-label", "Send message");
  sendButton.title = "Send message";
}

function renderAttachmentPreview() {
  if (!attachmentPreview) return;
  attachmentPreview.innerHTML = "";
  if (!selectedAttachment) {
    attachmentPreview.hidden = true;
    return;
  }

  attachmentPreview.hidden = false;
  const item = document.createElement("div");
  item.className = "attachment-item";

  if (selectedAttachment.type.startsWith("image/")) {
    const img = document.createElement("img");
    img.className = "attachment-thumb";
    img.src = selectedAttachmentData;
    img.alt = "";
    item.appendChild(img);
  } else {
    const thumb = document.createElement("div");
    thumb.className = "attachment-thumb";
    thumb.textContent = "TXT";
    thumb.style.display = "grid";
    thumb.style.placeItems = "center";
    thumb.style.fontSize = "10px";
    item.appendChild(thumb);
  }

  const name = document.createElement("span");
  name.className = "attachment-name";
  name.textContent = selectedAttachment.name;
  item.appendChild(name);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "attachment-remove";
  remove.setAttribute("aria-label", "Remove attachment");
  remove.textContent = "×";
  remove.addEventListener("click", clearAttachment);
  item.appendChild(remove);

  attachmentPreview.appendChild(item);
}

function clearAttachment() {
  selectedAttachment = null;
  selectedAttachmentData = "";
  if (fileInput) fileInput.value = "";
  if (attachmentPreview) {
    attachmentPreview.hidden = true;
    attachmentPreview.innerHTML = "";
  }
}

attachmentButton?.addEventListener("click", () => fileInput?.click());

fileInput?.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;

  const maxBytes = 10 * 1024 * 1024;
  if (file.size > maxBytes) {
    addMessage("assistant", "That file is too large. Please choose a file under 10 MB.");
    fileInput.value = "";
    return;
  }

  if (!(file.type.startsWith("image/") || file.type.startsWith("text/") ||
        ["application/json", "text/csv", "application/pdf"].includes(file.type))) {
    addMessage("assistant", "That file type is not supported yet.");
    fileInput.value = "";
    return;
  }

  selectedAttachment = file;

  if (file.type.startsWith("image/") || file.type === "application/pdf") {
    selectedAttachmentData = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  } else {
    selectedAttachmentData = await file.text();
  }

  renderAttachmentPreview();
});



chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (isLoading) {
    stopGeneration();
    return;
  }
  sendMessage();
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !isLoading) {
    event.preventDefault();
    sendMessage();
  }
});

settingsButton?.addEventListener("click", openSettings);
settingsClose?.addEventListener("click", closeSettings);
conversationClose?.addEventListener("click", closeConversationDrawer);
drawerBackdrop?.addEventListener("click", closeConversationDrawer);
newConversationButton?.addEventListener("click", startNewConversation);

window.addEventListener("load", () => {
  // Do not inject a canned assistant response. The first assistant message
  // shown in a conversation must come from the API.
});

