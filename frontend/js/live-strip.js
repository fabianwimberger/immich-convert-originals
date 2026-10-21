/** The live strip under the work area: the asset currently being processed,
 * its four pipeline steps, and how far the run has come.
 *
 * The backend reports "processing" and then the final outcome, not a step per
 * phase. The steps therefore show exactly what the outcome status proves: a
 * success has passed all four, a failed_upload has passed download and
 * transcode, and an asset still in flight shows no step as complete. */
class LiveStrip {
  constructor(root) {
    this.root = root;
    this.run = null;
    this.asset = null;
    wsClient.onMessage((msg) => this.onMessage(msg));
  }

  async init() {
    try {
      const resp = await api.get("/runs?status=running&limit=1");
      if (resp.items.length > 0) this.follow(resp.items[0]);
    } catch (err) {
      // Leave the strip in its idle state.
    }
    this.render();
  }

  follow(run) {
    this.run = run;
    this.asset = null;
    this.render();
  }

  onMessage(msg) {
    if (msg.type === "asset_progress") {
      if (!this.run) this.run = { id: msg.run_id, status: "running", processed_count: 0, total_assets: 0 };
      if (this.run.id !== msg.run_id) return;
      this.asset =
        msg.stage === "processing"
          ? { filename: msg.filename, status: "processing" }
          : {
              filename: msg.filename,
              status: msg.status,
              error: msg.error,
              target_format: msg.target_format,
              input_bytes: msg.input_bytes,
              output_bytes: msg.output_bytes,
            };
      this.render();
      return;
    }

    if (msg.type !== "run_started" && msg.type !== "run_progress" && msg.type !== "run_completed") {
      return;
    }
    if (this.run && this.run.id !== msg.run_id) return;
    if (!this.run) this.run = { id: msg.run_id, processed_count: 0, total_assets: 0 };
    if (msg.type === "run_started") this.run.status = "running";
    if (msg.type === "run_completed") this.run.status = msg.status;
    if (msg.processed_count !== undefined) {
      Object.assign(this.run, {
        processed_count: msg.processed_count,
        success_count: msg.success_count,
        skipped_count: msg.skipped_count,
        failed_count: msg.failed_count,
        total_assets: msg.total_assets,
      });
    }
    this.render();
    if (msg.type === "run_completed" && window.refreshShell) window.refreshShell();
  }

  stepLabels() {
    const local = settingsPanel && settingsPanel.settings && settingsPanel.settings.output_mode === "local";
    return local
      ? ["Download", "Transcode", "Save file", "Verify"]
      : ["Download", "Transcode", "Upload", "Verify"];
  }

  stepState(status, index) {
    if (!status || status === "processing" || status === "skipped") return "pending";
    if (status === "success" || status === "partial_success" || status === "saved_local") {
      return "done";
    }
    if (status === "dry_run_preview") return index <= 1 ? "done" : "pending";
    const failedAt = {
      failed_download: 0,
      failed_transcode: 1,
      failed_upload: 2,
      failed_copy: 2,
      failed_verification: 3,
    };
    if (Object.prototype.hasOwnProperty.call(failedAt, status)) {
      const step = failedAt[status];
      if (index < step) return "done";
      return index === step ? "failed" : "pending";
    }
    return "pending";
  }

  render() {
    if (!this.run) {
      this.root.innerHTML = `
        <div class="live__job">
          <div class="live__row"><span class="muted">No run in progress.</span></div>
          <p class="muted small">Start a run on Convert; the current asset appears here with its four steps.</p>
        </div>
        <div class="live__run">
          <div class="live__row">
            <span class="muted small">Saved in recent runs</span>
            <span class="num small">${typeof totalSaved === "function" ? fmtBytes(totalSaved()) : ""}</span>
          </div>
        </div>
      `;
      return;
    }

    const run = this.run;
    const pct =
      run.total_assets > 0 ? Math.round((run.processed_count / run.total_assets) * 100) : 0;
    const labels = this.stepLabels();
    const stateWords = { pending: "waiting", done: "done", failed: "failed" };
    const steps = labels
      .map((label, index) => {
        const state = this.stepState(this.asset && this.asset.status, index);
        return `<li class="step" data-state="${state}">${label} <span class="step__state">${stateWords[state]}</span></li>`;
      })
      .join("");

    const current = this.asset
      ? `
        <div class="live__row">
          <span class="live__name" title="${this.asset.filename}">${this.asset.filename}</span>
          <span class="${statusClass(this.asset.status)}">${prettyStatus(this.asset.status)}</span>
        </div>
        <ol class="steps" role="list">${steps}</ol>
      `
      : `
        <div class="live__row"><span class="muted">Waiting for the next asset…</span></div>
        <ol class="steps" role="list">${steps}</ol>
      `;

    this.root.innerHTML = `
      <div class="live__job">${current}</div>
      <div class="live__run">
        <div class="live__row">
          <span class="small muted">Run #${run.id}</span>
          <span class="num small">${run.processed_count} / ${run.total_assets} · ${pct}%</span>
        </div>
        <div class="progress"><span style="width:${pct}%"></span></div>
      </div>
    `;
  }
}
