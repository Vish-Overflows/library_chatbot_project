(function () {
  const currentScript = document.currentScript;
  const configuredUrl = currentScript && currentScript.dataset.chatUrl;
  const chatUrl = configuredUrl || new URL("/", currentScript ? currentScript.src : window.location.href).href;

  if (document.getElementById("gyanai-widget-root")) {
    return;
  }

  const root = document.createElement("div");
  root.id = "gyanai-widget-root";
  root.innerHTML = `
    <button class="gyanai-widget-button" type="button" aria-expanded="false" aria-controls="gyanai-widget-frame">
      <span class="gyanai-widget-orbit" aria-hidden="true">
        <span class="gyanai-widget-spark">AI</span>
      </span>
      <span class="gyanai-widget-button-text">
        <strong>Ask GyanAI</strong>
        <small>Library assistant</small>
      </span>
    </button>
    <section class="gyanai-widget-panel" aria-label="GyanAI Library Chatbot">
      <div class="gyanai-widget-header">
        <div class="gyanai-widget-title">
          <span class="gyanai-widget-mini-icon" aria-hidden="true">AI</span>
          <span>
            <strong>GyanAI</strong>
            <small>IITGN Library Assistant</small>
          </span>
        </div>
        <button class="gyanai-widget-close" type="button" aria-label="Close GyanAI">×</button>
      </div>
      <iframe id="gyanai-widget-frame" title="GyanAI Library Chatbot" src="${chatUrl}"></iframe>
    </section>
  `;

  const style = document.createElement("style");
  style.textContent = `
    #gyanai-widget-root {
      position: fixed;
      right: 22px;
      bottom: 22px;
      z-index: 2147483000;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .gyanai-widget-button {
      min-height: 62px;
      border: 0;
      border-radius: 999px;
      padding: 8px 18px 8px 8px;
      background: linear-gradient(135deg, #12395b 0%, #006b54 100%);
      color: #fff;
      box-shadow: 0 18px 42px rgba(18, 57, 91, 0.34);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 12px;
      transition: transform 160ms ease, box-shadow 160ms ease;
    }

    .gyanai-widget-button:hover {
      transform: translateY(-2px);
      box-shadow: 0 22px 54px rgba(18, 57, 91, 0.42);
    }

    .gyanai-widget-orbit {
      width: 46px;
      height: 46px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 32% 28%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.2) 38%, transparent 39%),
        rgba(255, 255, 255, 0.18);
      display: grid;
      place-items: center;
      position: relative;
      border: 1px solid rgba(255, 255, 255, 0.38);
    }

    .gyanai-widget-orbit::after {
      content: "";
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      border: 1px solid rgba(255, 255, 255, 0.34);
      border-top-color: rgba(196, 138, 44, 0.95);
    }

    .gyanai-widget-spark,
    .gyanai-widget-mini-icon {
      font-weight: 900;
      letter-spacing: 0;
    }

    .gyanai-widget-button-text {
      display: grid;
      text-align: left;
      line-height: 1.1;
    }

    .gyanai-widget-button-text strong {
      font-size: 15px;
    }

    .gyanai-widget-button-text small {
      margin-top: 3px;
      color: rgba(255, 255, 255, 0.78);
      font-size: 12px;
    }

    .gyanai-widget-panel {
      display: none;
      position: fixed;
      right: 22px;
      bottom: 84px;
      width: min(450px, calc(100vw - 28px));
      height: min(720px, calc(100vh - 112px));
      overflow: hidden;
      border: 1px solid #d7e2ea;
      border-radius: 16px;
      background: #fff;
      box-shadow: 0 24px 64px rgba(18, 33, 43, 0.26);
    }

    #gyanai-widget-root.open .gyanai-widget-panel {
      display: grid;
      grid-template-rows: 56px minmax(0, 1fr);
    }

    .gyanai-widget-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px 0 16px;
      background: linear-gradient(135deg, #12395b 0%, #0d2e4b 58%, #006b54 100%);
      color: #fff;
    }

    .gyanai-widget-title {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .gyanai-widget-title span:last-child {
      display: grid;
      line-height: 1.1;
    }

    .gyanai-widget-title small {
      margin-top: 3px;
      color: rgba(255, 255, 255, 0.74);
      font-size: 12px;
    }

    .gyanai-widget-mini-icon {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.16);
      border: 1px solid rgba(255, 255, 255, 0.32);
      display: grid;
      place-items: center;
      color: white;
      font-size: 12px;
    }

    .gyanai-widget-close {
      width: 34px;
      height: 34px;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: #fff;
      font-size: 24px;
      line-height: 1;
      cursor: pointer;
    }

    #gyanai-widget-frame {
      width: 100%;
      height: 100%;
      border: 0;
      background: #fff;
    }

    @media (max-width: 560px) {
      #gyanai-widget-root {
        right: 12px;
        bottom: 12px;
      }

      .gyanai-widget-panel {
        right: 8px;
        bottom: 72px;
        width: calc(100vw - 16px);
        height: calc(100vh - 88px);
      }
    }
  `;

  document.head.appendChild(style);
  document.body.appendChild(root);

  const button = root.querySelector(".gyanai-widget-button");
  const close = root.querySelector(".gyanai-widget-close");

  function setOpen(value) {
    root.classList.toggle("open", value);
    button.setAttribute("aria-expanded", String(value));
    const label = root.querySelector(".gyanai-widget-button-text strong");
    const sublabel = root.querySelector(".gyanai-widget-button-text small");
    if (label && sublabel) {
      label.textContent = value ? "Close GyanAI" : "Ask GyanAI";
      sublabel.textContent = value ? "Hide assistant" : "Library assistant";
    }
  }

  button.addEventListener("click", () => {
    setOpen(!root.classList.contains("open"));
  });
  close.addEventListener("click", () => setOpen(false));
})();
