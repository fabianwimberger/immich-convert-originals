/** Past runs: list, drill into per-asset outcomes, retry-failed, export CSV. */
class RunHistory {
  constructor(root) {
    this.root = root;
    this.runs = [];
    this.openRunId = null;
    this.outcomes = [];
  }

  async init() {
    await this.load();
    this.render();
  }

  async load() {
    const resp = await api.get("/runs?limit=50");
    this.runs = resp.items;
  }

  async refresh() {
    await this.load();
    this.render();
  }

  render() {
    if (this.runs.length === 0) {
      this.root.innerHTML = `<section class="panel"><p class="placeholder">No runs yet.</p></section>`;
      return;
    }

    const rows = this.runs
      .map((r) => {
        const pct = r.total_assets > 0 ? Math.round((r.processed_count / r.total_assets) * 100) : 0;
        return `
          <tr class="run-row" data-id="${r.id}">
            <td>#${r.id}</td>
            <td><span class="run-status status-${r.status}">${r.status}</span></td>
            <td>${new Date(r.created_at).toLocaleString()}</td>
            <td>${r.dry_run ? "dry run" : ""}</td>
            <td>${r.processed_count}/${r.total_assets} (${pct}%)</td>
            <td class="status-ok">${r.success_count}</td>
            <td>${r.skipped_count}</td>
            <td class="status-error">${r.failed_count}</td>
            <td>${this._bytesSaved(r)}</td>
          </tr>
        `;
      })
      .join("");

    this.root.innerHTML = `
      <section class="panel">
        <div class="row">
          <h2>Run History</h2>
          <button id="btn-refresh-history">Refresh</button>
        </div>
        <div class="table-wrap">
          <table class="run-table">
            <thead>
              <tr>
                <th>Run</th><th>Status</th><th>Started</th><th></th>
                <th>Progress</th><th>OK</th><th>Skip</th><th>Fail</th><th>Saved</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
      <section class="panel" id="run-detail" style="display:none"></section>
    `;

    this.root.querySelector("#btn-refresh-history").addEventListener("click", () => this.refresh());
    this.root.querySelectorAll(".run-row").forEach((row) => {
      row.addEventListener("click", () => this.openRun(parseInt(row.dataset.id, 10)));
    });
  }

  _bytesSaved(r) {
    return this._savedLabel(r.input_bytes, r.output_bytes);
  }

  _savedLabel(inputBytes, outputBytes) {
    if (!inputBytes) return "";
    const saved = inputBytes - outputBytes;
    const pct = ((saved / inputBytes) * 100).toFixed(0);
    return `${this._fmtBytes(saved)} (${pct}%)`;
  }

  _prettyStatus(status) {
    const labels = {
      success: "Converted",
      partial_success: "Converted (cleanup needed)",
      dry_run_preview: "Would convert",
      skipped: "Skipped",
      failed_download: "Failed: download",
      failed_transcode: "Failed: transcode",
      failed_upload: "Failed: upload",
      failed_copy: "Failed: metadata copy",
      failed_verification: "Failed: verification",
    };
    return labels[status] || status.replace(/_/g, " ");
  }

  _fmtBytes(n) {
    if (Math.abs(n) < 1024) return `${n} B`;
    const units = ["KB", "MB", "GB"];
    let val = n;
    let i = -1;
    do {
      val /= 1024;
      i++;
    } while (Math.abs(val) >= 1024 && i < units.length - 1);
    return `${val.toFixed(1)} ${units[i]}`;
  }

  async openRun(runId) {
    this.openRunId = runId;
    const detail = this.root.querySelector("#run-detail");
    detail.style.display = "block";
    detail.innerHTML = `<p class="placeholder">Loading…</p>`;

    const outcomesResp = await api.get(`/runs/${runId}/assets?limit=200`);
    this.outcomes = outcomesResp.items;
    const run = this.runs.find((r) => r.id === runId);
    const failedCount = run ? run.failed_count : 0;

    const rows = this.outcomes
      .map(
        (o) => `
          <tr>
            <td>${o.filename}</td>
            <td>${this._prettyStatus(o.status)}</td>
            <td>${o.target_format || ""}</td>
            <td>${o.input_bytes ? `${this._fmtBytes(o.input_bytes)} &rarr; ${this._fmtBytes(o.output_bytes)}` : ""}</td>
            <td>${this._savedLabel(o.input_bytes, o.output_bytes)}</td>
            <td>${o.error || ""}</td>
          </tr>
        `
      )
      .join("");

    detail.innerHTML = `
      <div class="row">
        <h3>Run #${runId} details</h3>
        <button id="btn-retry-failed" ${failedCount ? "" : "disabled"}>Retry ${failedCount} failed</button>
        <a id="btn-export-failures" href="/api/runs/${runId}/export-failures">Export failures CSV</a>
      </div>
      <div class="table-wrap">
        <table class="run-table">
          <thead><tr><th>Filename</th><th>Status</th><th>Format</th><th>Size</th><th>Saved</th><th>Error</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="6" class="placeholder">No outcomes recorded.</td></tr>'}</tbody>
        </table>
      </div>
    `;

    const retryBtn = detail.querySelector("#btn-retry-failed");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => this.retryFailed(runId));
    }
  }

  async retryFailed(runId) {
    try {
      const newRun = await api.post(`/runs/${runId}/retry-failed`);
      await this.refresh();
      if (window.switchToActiveRun) window.switchToActiveRun(newRun.id);
    } catch (err) {
      alert(err.message);
    }
  }
}
