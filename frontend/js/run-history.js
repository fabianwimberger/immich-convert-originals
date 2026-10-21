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
      this.root.innerHTML = `
        <section class="panel">
          <div class="empty">
            <p>No runs yet.</p>
            <p class="small">Start one on the Convert tab; every run is kept here with its per-asset outcomes.</p>
          </div>
        </section>
      `;
      return;
    }

    const rows = this.runs
      .map((r) => {
        const pct = r.total_assets > 0 ? Math.round((r.processed_count / r.total_assets) * 100) : 0;
        return `
          <tr class="run-row" data-id="${r.id}" tabindex="0">
            <td>#${r.id}${r.dry_run ? ' <span class="muted small">dry run</span>' : ""}</td>
            <td><span class="${runStatusClass(r.status)}">${prettyRunStatus(r.status)}</span></td>
            <td class="col-wide">${new Date(r.created_at).toLocaleString()}</td>
            <td>
              <span class="run-bar">
                <span class="bar"><span style="width:${pct}%"></span></span>
                <span class="num">${r.processed_count}/${r.total_assets}</span>
              </span>
            </td>
            <td class="r num">${r.success_count}</td>
            <td class="r num col-wide">${r.skipped_count}</td>
            <td class="r num">${r.failed_count}</td>
            <td class="r num col-wide">${savedLabel(r.input_bytes, r.output_bytes)}</td>
          </tr>
        `;
      })
      .join("");

    this.root.innerHTML = `
      <div class="toolbar">
        <span class="table-count">${this.runs.length} most recent runs</span>
        <button id="btn-refresh-history" class="btn btn--quiet btn--small end" type="button">Refresh</button>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>State</th>
              <th class="col-wide">Started</th>
              <th>Progress</th>
              <th class="r">Succeeded</th>
              <th class="r col-wide">Skipped</th>
              <th class="r">Failed</th>
              <th class="r col-wide">Saved</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <section class="panel run-detail" id="run-detail" style="display:none"></section>
    `;

    this.root.querySelector("#btn-refresh-history").addEventListener("click", () => this.refresh());
    this.root.querySelectorAll(".run-row").forEach((row) => {
      const open = () => this.openRun(parseInt(row.dataset.id, 10));
      row.addEventListener("click", open);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });
    });
  }

  async openRun(runId) {
    this.openRunId = runId;
    const detail = this.root.querySelector("#run-detail");
    detail.style.display = "block";
    detail.innerHTML = `<p class="muted">Loading…</p>`;

    const outcomesResp = await api.get(`/runs/${runId}/assets?limit=200`);
    this.outcomes = outcomesResp.items;
    const run = this.runs.find((r) => r.id === runId);
    const failedCount = run ? run.failed_count : 0;

    const rows = this.outcomes
      .map(
        (o) => `
          <tr>
            <td>${o.filename}</td>
            <td><span class="${statusClass(o.status)}">${prettyStatus(o.status)}</span></td>
            <td class="col-wide">${o.target_format || ""}</td>
            <td class="col-wide r num">${o.input_bytes ? `${fmtBytes(o.input_bytes)} &rarr; ${fmtBytes(o.output_bytes)}` : ""}</td>
            <td class="r num">${savedLabel(o.input_bytes, o.output_bytes)}</td>
            <td class="col-wide wrap">${o.error || ""}</td>
          </tr>
        `
      )
      .join("");

    detail.innerHTML = `
      <div class="panel__head">
        <h2 class="h4">Run #${runId}</h2>
        <span class="small muted">${this.outcomes.length} outcomes</span>
      </div>
      <div class="actions">
        <button id="btn-retry-failed" class="btn btn--quiet btn--small" type="button" ${failedCount ? "" : "disabled"}>Retry ${failedCount} failed</button>
        <a id="btn-export-failures" class="btn btn--text btn--small" href="/api/runs/${runId}/export-failures">Export failures CSV</a>
        <span id="retry-status"></span>
      </div>
      <div class="table-scroll log-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>File</th>
              <th>State</th>
              <th class="col-wide">Format</th>
              <th class="col-wide r">Size</th>
              <th class="r">Saved</th>
              <th class="col-wide">Error</th>
            </tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="6" class="muted">No outcomes recorded.</td></tr>'}</tbody>
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
      const statusEl = this.root.querySelector("#retry-status");
      if (statusEl) {
        statusEl.textContent = err.message;
        statusEl.className = "status status--fail";
      }
    }
  }
}
