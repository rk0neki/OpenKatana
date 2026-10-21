import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function showStudio(result) {
  if (!result?.studio || !/^http:\/\/127\.0\.0\.1:\d+\/?$/.test(result.studio)) return;
  document.getElementById('openkatana-studio-link')?.remove();
  const notice = document.createElement('aside');
  notice.id = 'openkatana-studio-link';
  notice.setAttribute('aria-label', 'OpenKatana Studio ready');
  notice.style.cssText = 'position:fixed;left:70px;bottom:24px;z-index:1000;max-width:calc(100vw - 110px);padding:16px;display:flex;gap:16px;align-items:center;background:#202125;color:#fff;border:1px solid #62636a;border-radius:12px;box-shadow:0 4px 18px #0005';
  const label = document.createElement('span'); label.textContent = 'OpenKatana · Studio ready';
  const link = document.createElement('a'); link.textContent = 'Open Studio ↗';
  link.href = result.studio; link.target = '_blank'; link.rel = 'noopener';
  link.style.cssText = 'color:#fff;text-decoration:underline;font-weight:600';
  const close = document.createElement('button'); close.textContent = '×';
  close.setAttribute('aria-label', 'Dismiss Studio link'); close.onclick = () => notice.remove();
  notice.append(label, link, close); document.body.append(notice);
}

// Graph-mode convenience. App Mode also receives standard text/image outputs.
// Only this local server supplies job data; text is never interpreted as HTML.
app.registerExtension({
  name: "OpenKatana.LocalApps",
  setup() {
    // App Mode can process execution output without a graph node onExecuted call.
    api.addEventListener('executed', ({ detail }) => showStudio(detail.output?.openkatana?.[0]));
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData.name.startsWith("OpenKatana")) return;
    const prior = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      prior?.apply(this, arguments);
      const result = message.openkatana?.[0];
      if (!result) return;
      if (!this.openkatanaResult) {
        this.openkatanaResult = this.addWidget("text", "Result", "", () => {}, { multiline: true });
        this.openkatanaResult.serialize = false;
      }
      this.openkatanaResult.value = JSON.stringify(result, null, 2);
      if (result.studio && /^http:\/\/127\.0\.0\.1:\d+\/?$/.test(result.studio)) {
        this.openkatanaStudioURL = result.studio;
        if (!this.openkatanaStudioButton) {
          this.openkatanaStudioButton = this.addWidget("button", "Open Studio ↗", null,
            () => window.open(this.openkatanaStudioURL, "_blank", "noopener"));
          this.openkatanaStudioButton.serialize = false;
        }
      }
      const job = result.job_id;
      if (result.state === "running" && /^[a-f0-9]{32}$/.test(job)) {
        this.openkatanaJob = job;
        const poll = async () => {
          if (this.openkatanaJob !== job || !this.graph) return;
          try {
            const response = await api.fetchApi(`/openkatana/jobs/${job}`);
            const status = await response.json();
            if (!response.ok) throw new Error(status.error || "Status unavailable");
            this.openkatanaResult.value = JSON.stringify(status, null, 2);
            app.nodeOutputs[this.id] = { ...app.nodeOutputs[this.id], text: [this.openkatanaResult.value] };
            this.setDirtyCanvas(true, true);
            if (status.state === "running") setTimeout(poll, 2000);
          } catch (error) {
            this.openkatanaResult.value = `Status unavailable: ${error.message}. Use Background job with ${job}.`;
          }
        };
        setTimeout(poll, 1500);
      }
    };
  }
});
