/** Live progress view for a single run: summary panel plus a scrolling
 * per-asset log, driven by WebSocket events. Each row starts as "processing"
 * and resolves in place once its outcome arrives, so concurrent workers each
 * get their own line instead of a single shared status.
 *
 * Row and summary updates are batched into one requestAnimationFrame flush
 * instead of applied per message: a fast bulk-skip run can emit well over a
 * thousand messages a second, and doing a DOM write (plus a scroll-position
 * read, which forces a synchronous layout) on every single one is enough to
 * lock up the tab. */
class ActiveRun {
  constructor(root) {
    this.root = root;
    this.runId = null;
    this.run = null;
    this.log = []; // ordered per-asset entries, updated in place as they resolve
    this._logIndex = new Map(); // asset_id -> index into this.log
    this._rowEls = new Map(); // asset_id -> rendered <tr>
    this._dirtyRows = new Set(); // asset_ids awaiting the next flush
    this._summaryDirty = false;
    this._flushHandle = null;
    this._unsubscribe = null;
    this.onBack = null; // set by RunPanel: return to the config screen
  }

  async show(runId) {
    this.runId = runId;
    this.log = [];
    this._logIndex.clear();
    this._rowEls.clear();
    this._dirtyRows.clear();
    this._summaryDirty = false;
    if (this._flushHandle !== null) {
      cancelAnimationFrame(this._flushHandle);
      this._flushHandle = null;
    }
    this.run = await api.get(`/runs/${runId}`);
    this._renderShell();
    this._renderSummary();
    this._renderLog();
    if (window.liveStrip) window.liveStrip.follow(this.run);

    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = wsClient.onMessage((msg) => this._handleMessage(msg));
  }

  _handleMessage(msg) {
    if (msg.run_id !== this.runId) return;

    if (msg.type === "asset_progress") {
      if (msg.stage === "processing") {
        const entry = { asset_id: msg.asset_id, filename: msg.filename, status: "processing" };
        this._logIndex.set(msg.asset_id, this.log.length);
        this.log.push(entry);
      } else {
        const entry = {
          asset_id: msg.asset_id,
          filename: msg.filename,
          status: msg.status,
          error: msg.error,
          target_format: msg.target_format,
          input_bytes: msg.input_bytes,
          output_bytes: msg.output_bytes,
        };
        const idx = this._logIndex.get(msg.asset_id);
        if (idx !== undefined) {
          this.log[idx] = entry;
        } else {
          this._logIndex.set(msg.asset_id, this.log.length);
          this.log.push(entry);
        }
      }
      this._dirtyRows.add(msg.asset_id);
      this._scheduleFlush();
    } else if (msg.type === "run_progress") {
      this._applyCounters(msg);
      this._summaryDirty = true;
      this._scheduleFlush();
    } else if (msg.type === "run_completed") {
      this._applyCounters(msg);
      this.run.status = msg.status;
      this._renderSummary();
      if (window.refreshShell) window.refreshShell();
    } else if (msg.type === "run_started") {
      this.run.status = "running";
      this._renderSummary();
    }
  }

  _applyCounters(msg) {
    if (msg.processed_count === undefined) return;
    Object.assign(this.run, {
      processed_count: msg.processed_count,
      success_count: msg.success_count,
      skipped_count: msg.skipped_count,
      failed_count: msg.failed_count,
      total_assets: msg.total_assets,
    });
  }

  _scheduleFlush() {
    if (this._flushHandle !== null) return;
    this._flushHandle = requestAnimationFrame(() => this._flush());
  }

  _flush() {
    this._flushHandle = null;
    if (this._summaryDirty) {
      this._summaryDirty = false;
      this._renderSummary();
    }
    if (this._dirtyRows.size > 0) {
      this._flushRows();
    }
  }

  async cancel() {
    await api.del(`/runs/${this.runId}`);
    this.run = await api.get(`/runs/${this.runId}`);
    this._renderSummary();
  }

  _renderShell() {
    this.root.innerHTML = `
      <section class="panel" id="run-summary"></section>
      <section class="panel">
        <div class="panel__head">
          <h2 class="h4">Per-asset log</h2>
        </div>
        <div class="table-scroll log-scroll" id="run-log-scroll">
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
            <tbody id="run-log-body"></tbody>
          </table>
        </div>
      </section>
    `;
  }

  _renderSummary() {
    const r = this.run;
    const pct = r.total_assets > 0 ? Math.round((r.processed_count / r.total_assets) * 100) : 0;
    const canCancel = r.status === "queued" || r.status === "running";
    const summary = this.root.querySelector("#run-summary");

    summary.innerHTML = `
      <div class="panel__head">
        <h2 class="h4">Run #${r.id}</h2>
        <span class="${runStatusClass(r.status)}">${prettyRunStatus(r.status)}</span>
      </div>
      ${r.dry_run ? '<p class="muted small">Dry run, no changes will be made.</p>' : ""}
      <div class="run-progress">
        <div class="progress"><span style="width:${pct}%"></span></div>
        <p class="small num muted">${r.processed_count} / ${r.total_assets} processed (${pct}%)</p>
      </div>
      <div class="run-counts">
        <span class="status status--ok">${r.success_count} succeeded</span>
        <span class="status">${r.skipped_count} skipped</span>
        <span class="status status--fail">${r.failed_count} failed</span>
      </div>
      ${r.error_message ? `<p class="${statusClass("failed_error")}">${r.error_message}</p>` : ""}
      <div class="actions">
        ${
          canCancel
            ? '<button id="btn-cancel-run" class="btn btn--quiet btn--small" type="button">Cancel run</button>'
            : '<button id="btn-back-to-config" class="btn btn--small" type="button">Start another run</button>'
        }
      </div>
    `;

    const cancelBtn = summary.querySelector("#btn-cancel-run");
    if (cancelBtn) cancelBtn.addEventListener("click", () => this.cancel());
    const backBtn = summary.querySelector("#btn-back-to-config");
    if (backBtn) backBtn.addEventListener("click", () => this.onBack && this.onBack());
  }

  _renderLog() {
    const body = this.root.querySelector("#run-log-body");
    if (!body) return;
    body.innerHTML = `<tr><td colspan="6" class="muted">Waiting for the first asset…</td></tr>`;
  }

  _rowCells(o) {
    return `
      <td>${o.filename}</td>
      <td><span class="${statusClass(o.status)}">${prettyStatus(o.status)}</span></td>
      <td class="col-wide">${o.target_format || ""}</td>
      <td class="col-wide r num">${o.input_bytes ? `${fmtBytes(o.input_bytes)} &rarr; ${fmtBytes(o.output_bytes)}` : ""}</td>
      <td class="r num">${savedLabel(o.input_bytes, o.output_bytes)}</td>
      <td class="col-wide wrap">${o.error || ""}</td>
    `;
  }

  // Applies every row queued since the last flush in one batch: a single
  // scroll-position read/write and a single reflow, no matter how many
  // messages arrived in between.
  _flushRows() {
    const scrollEl = this.root.querySelector("#run-log-scroll");
    const body = this.root.querySelector("#run-log-body");
    if (!body) {
      this._dirtyRows.clear();
      return;
    }

    const nearBottom = scrollEl.scrollTop + scrollEl.clientHeight >= scrollEl.scrollHeight - 24;

    if (this._rowEls.size === 0) {
      body.innerHTML = "";
    }

    const fragment = document.createDocumentFragment();
    for (const assetId of this._dirtyRows) {
      const idx = this._logIndex.get(assetId);
      if (idx === undefined) continue;
      const entry = this.log[idx];

      let tr = this._rowEls.get(assetId);
      if (!tr) {
        tr = document.createElement("tr");
        this._rowEls.set(assetId, tr);
        fragment.appendChild(tr);
      }
      tr.innerHTML = this._rowCells(entry);
    }
    if (fragment.childNodes.length > 0) {
      body.appendChild(fragment);
    }
    this._dirtyRows.clear();

    if (nearBottom) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }
}
