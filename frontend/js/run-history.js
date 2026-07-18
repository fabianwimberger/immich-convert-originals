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
            <td>${savedLabel(r.input_bytes, r.output_bytes)}</td>
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
            <td>${prettyStatus(o.status)}</td>
            <td>${o.target_format || ""}</td>
            <td>${o.input_bytes ? `${fmtBytes(o.input_bytes)} &rarr; ${fmtBytes(o.output_bytes)}` : ""}</td>
            <td>${savedLabel(o.input_bytes, o.output_bytes)}</td>
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
