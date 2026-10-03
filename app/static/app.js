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
    .replace(/            renderAssistantMessage(assistantMessage, payload.message || fullAnswer);
          }

          scrollToActive(assistantGroup, "smooth");/$/, "");

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

