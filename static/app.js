const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const messages = document.getElementById("messages");
const messageTemplate = document.getElementById("message-template");
const sourceTemplate = document.getElementById("source-template");
const feedbackPanel = document.getElementById("feedback-panel");
const sendButton = document.getElementById("send-button");
const modeIndicator = document.getElementById("mode-indicator");

let sessionId = window.localStorage.getItem("iitgn-library-session") || "";
let isSending = false;

const SOURCE_LABELS = {
  faq: "FAQ",
  catalog: "Catalog",
  ejournal: "E-journal",
  repository_publication: "Repository",
};

function formatSourceMeta(source) {
  const metadata = source.metadata || {};
  const parts = [
    metadata.collection,
    metadata.coverage ? `Coverage: ${metadata.coverage}` : "",
    metadata.availability,
    metadata.date ? `Date: ${metadata.date}` : "",
    metadata.doi ? `DOI: ${metadata.doi}` : "",
    source.confidence ? `Confidence: ${source.confidence.toFixed(2)}` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function appendMessage({ role, text, sources = [], relatedQuestions = [], loading = false }) {
  const fragment = messageTemplate.content.cloneNode(true);
  const article = fragment.querySelector(".message");
  const textNode = fragment.querySelector(".message-text");
  const sourceList = fragment.querySelector(".source-list");
  const relatedBox = fragment.querySelector(".related");
  const relatedList = fragment.querySelector(".related-list");

  article.classList.add(role);
  if (loading) {
    article.classList.add("loading");
  }
  textNode.textContent = text;

  sources.slice(0, 4).forEach((source) => {
    const sourceFragment = sourceTemplate.content.cloneNode(true);
    const card = sourceFragment.querySelector(".source-card");
    const type = sourceFragment.querySelector(".source-type");
    const title = sourceFragment.querySelector(".source-title");
    const meta = sourceFragment.querySelector(".source-meta");

    card.href = source.source_url || "#";
    type.textContent = SOURCE_LABELS[source.source_type] || source.source_type || "Source";
    title.textContent = source.title || "Library source";
    meta.textContent = formatSourceMeta(source);
    sourceList.appendChild(sourceFragment);
  });

  if (sources.length > 0) {
    sourceList.classList.remove("hidden");
  }

  if (relatedQuestions.length > 0) {
    relatedBox.classList.remove("hidden");
    relatedQuestions.forEach((question) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "related-button";
      button.textContent = question;
      button.addEventListener("click", () => {
        input.value = question;
        input.focus();
      });
      relatedList.appendChild(button);
    });
  }

  messages.appendChild(fragment);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function setSending(value) {
  isSending = value;
  sendButton.disabled = value;
  input.disabled = value;
  modeIndicator.textContent = value ? "Searching" : "Ready";
}

async function sendMessage(message) {
  if (isSending) {
    return;
  }

  appendMessage({ role: "user", text: message });
  input.value = "";
  feedbackPanel.classList.add("hidden");
  setSending(true);
  const loadingMessage = appendMessage({
    role: "assistant",
    text: "Searching IITGN Library sources and composing a grounded answer...",
    loading: true,
  });

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: sessionId || null,
      }),
    });

    loadingMessage.remove();

    if (!response.ok) {
      appendMessage({
        role: "assistant",
        text: "The chatbot is unavailable right now. Please try again shortly.",
      });
      return;
    }

    const data = await response.json();
    sessionId = data.session_id;
    window.localStorage.setItem("iitgn-library-session", sessionId);
    modeIndicator.textContent = data.response_mode === "llm" ? "Grounded LLM" : "Retrieved";

    appendMessage({
      role: "assistant",
      text: data.answer,
      sources: data.sources || [],
      relatedQuestions: data.related_questions || [],
    });
    feedbackPanel.classList.remove("hidden");
  } catch (error) {
    loadingMessage.remove();
    appendMessage({
      role: "assistant",
      text: "I could not reach the chatbot service. Please check the server and try again.",
    });
  } finally {
    setSending(false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) {
    return;
  }
  await sendMessage(message);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    await sendMessage(button.dataset.prompt);
  });
});

document.querySelectorAll(".feedback-button").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!sessionId) {
      return;
    }

    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        helpful: button.dataset.helpful === "true",
        comment: "",
      }),
    });

    feedbackPanel.classList.add("hidden");
  });
});
