/** Live progress view for a single run, driven by WebSocket events. */
class ActiveRun {
  constructor(root) {
    this.root = root;
    this.runId = null;
    this.run = null;
    this.currentAssets = new Map(); // asset_id -> filename, while "processing"
    this._unsubscribe = null;
    this.onBack = null; // set by RunPanel: return to the config screen
  }

  async show(runId) {
    this.runId = runId;
    this.currentAssets.clear();
    this.run = await api.get(`/runs/${runId}`);
    this.render();

    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = wsClient.onMessage((msg) => this._handleMessage(msg));
  }

  _handleMessage(msg) {
    if (msg.run_id !== this.runId) return;

    if (msg.type === "asset_progress") {
      if (msg.stage === "processing") {
        this.currentAssets.set(msg.asset_id, msg.filename);
      } else {
        this.currentAssets.delete(msg.asset_id);
      }
      this.render();
    } else if (msg.type === "run_progress") {
      Object.assign(this.run, {
        processed_count: msg.processed_count,
        success_count: msg.success_count,
        skipped_count: msg.skipped_count,
        failed_count: msg.failed_count,
        total_assets: msg.total_assets,
      });
      this.render();
    } else if (msg.type === "run_completed") {
      this.run.status = msg.status;
      this.currentAssets.clear();
      this.render();
    } else if (msg.type === "run_started") {
      this.run.status = "running";
      this.render();
    }
  }

  async cancel() {
    await api.del(`/runs/${this.runId}`);
    this.run = await api.get(`/runs/${this.runId}`);
    this.render();
  }

  render() {
    const r = this.run;
    const pct = r.total_assets > 0 ? Math.round((r.processed_count / r.total_assets) * 100) : 0;
    const canCancel = r.status === "queued" || r.status === "running";
    const active = [...this.currentAssets.values()];

    this.root.innerHTML = `
      <section class="panel">
        <h2>Run #${r.id} <span class="run-status status-${r.status}">${r.status}</span></h2>
        ${r.dry_run ? '<p class="placeholder">Dry run &mdash; no changes will be made.</p>' : ""}
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        <p>${r.processed_count} / ${r.total_assets} processed (${pct}%)</p>
        <div class="row run-counts">
          <span class="status-ok">${r.success_count} succeeded</span>
          <span>${r.skipped_count} skipped</span>
          <span class="status-error">${r.failed_count} failed</span>
        </div>
        ${
          active.length
            ? `<p class="placeholder">Processing: ${active.join(", ")}</p>`
            : ""
        }
        ${r.error_message ? `<p class="status-error">${r.error_message}</p>` : ""}
        <div class="row">
          ${
            canCancel
              ? '<button id="btn-cancel-run">Cancel</button>'
              : '<button id="btn-back-to-config" class="primary">Start Another Run</button>'
          }
        </div>
      </section>
    `;

    const cancelBtn = this.root.querySelector("#btn-cancel-run");
    if (cancelBtn) cancelBtn.addEventListener("click", () => this.cancel());
    const backBtn = this.root.querySelector("#btn-back-to-config");
    if (backBtn) backBtn.addEventListener("click", () => this.onBack && this.onBack());
  }
}
