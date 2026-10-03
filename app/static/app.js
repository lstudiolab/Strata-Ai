let isLoading = false;
let sessionId = localStorage.getItem("strata_session_id");

const messagesContainer = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatForm = document.getElementById("chatForm");
const attachmentButton = document.getElementById("attachmentButton");
const fileInput = document.getElementById("fileInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const contextPanel = document.getElementById("contextPanel");
const contextInput = document.getElementById("contextInput");
const contextClose = document.getElementById("contextClose");
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

function addMessage(role, text, isStatus = false, attachment = null) {
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

  if (role === "assistant" && !isStatus) {
    const actions = document.createElement("div");
    actions.className = "response-actions";

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
  if (!message && !selectedAttachmentData) return;

  isLoading = true;
  messageInput.disabled = true;
  sendButton.disabled = true;
  messageInput.value = "";

  const displayMessage = message || (selectedAttachment?.name ? "Attached: " + selectedAttachment.name : "Image");
  const sentAttachment = selectedAttachment && selectedAttachment.type.startsWith("image/")
    ? { data: selectedAttachmentData, name: selectedAttachment.name }
    : null;
  const userMessage = addMessage("user", displayMessage, false, sentAttachment);
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

          renderAssistantMessage(assistantMessage, fullAnswer);
          scrollToActive(assistantGroup, "auto");
        } else if (payload.type === "answer") {
          removeLastStatus();

          if (!assistantMessage) {
            assistantMessage = addMessage("assistant", payload.message || "");
            assistantGroup = assistantMessage.parentElement;
          } else {
            renderAssistantMessage(assistantMessage, payload.message || fullAnswer);
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
    clearAttachment();
  }
}

function resetInput() {
  isLoading = false;
  messageInput.disabled = false;
  sendButton.disabled = false;
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

contextClose?.addEventListener("click", toggleContextPanel);

contextInput?.addEventListener("input", () => {
  const count = contextInput.value.length;
  attachmentButton?.setAttribute("aria-label", count ? "Add a file" : "Add a photo or file");
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
  if (!messagesContainer.children.length) addMessage("assistant", "Hi, I'm Strata. How can I help?");
});

