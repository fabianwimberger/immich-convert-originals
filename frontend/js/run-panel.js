/** Configure and start a run: whole library, one album, a date range, or a browser selection. */
class RunPanel {
  constructor(root, activeRun) {
    this.root = root;
    this.activeRun = activeRun;
    this.configEl = null;
    this.activeEl = null;
    this.albums = [];
    this.mode = null; // "library" | "album" | "date" | "selection"
  }

  async init() {
    this.root.innerHTML = `
      <div id="run-config"></div>
      <div id="run-active-container" style="display:none"></div>
    `;
    this.configEl = this.root.querySelector("#run-config");
    this.activeEl = this.root.querySelector("#run-active-container");
    this.activeRun.onBack = () => this.showConfig();

    try {
      const resp = await api.get("/albums");
      this.albums = resp.items;
    } catch (err) {
      this.albums = [];
    }

    this.renderConfig();
  }

  /** Called when the Convert tab is (re-)shown, so the selection count and
   * album list stay current without clobbering a mode the user already chose. */
  refresh() {
    if (this.configEl && this.configEl.style.display !== "none") {
      this.renderConfig();
    }
  }

  showConfig() {
    this.configEl.style.display = "block";
    this.activeEl.style.display = "none";
    this.renderConfig();
  }

  renderConfig() {
    const selectedCount = assetBrowser ? assetBrowser.selected.size : 0;
    if (!this.mode) this.mode = selectedCount ? "selection" : "library";
    this.configEl.style.display = "block";
    this.activeEl.style.display = "none";

    const modes = [
      { id: "library", label: "Whole library" },
      ...(this.albums.length ? [{ id: "album", label: "Album" }] : []),
      { id: "date", label: "Date range" },
      { id: "selection", label: selectedCount ? `Selection (${selectedCount})` : "Selection" },
    ];
    const modeButtons = modes
      .map(
        (m) =>
          `<button type="button" class="mode-btn ${this.mode === m.id ? "active" : ""}" data-mode="${m.id}">${m.label}</button>`
      )
      .join("");

    this.configEl.innerHTML = `
      <section class="panel">
        <h2>Start a Run</h2>
        <div class="mode-picker" role="tablist">${modeButtons}</div>
        ${this._renderModeBody(selectedCount)}
        <label><input id="run-dry-run" type="checkbox" checked /> Dry run (preview only, no changes)</label>
        <label>Concurrency
          <input id="run-concurrency" type="number" min="1" max="32" placeholder="use default" />
        </label>
        <div class="row">
          <button id="btn-start-run" class="primary">Start Run</button>
          <span id="start-run-status"></span>
        </div>
      </section>
    `;

    this.configEl.querySelectorAll(".mode-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        this.mode = btn.dataset.mode;
        this.renderConfig();
      })
    );

    this.configEl
      .querySelector("#btn-start-run")
      .addEventListener("click", () => this.startRun());
  }

  _renderModeBody(selectedCount) {
    if (this.mode === "selection") {
      return selectedCount
        ? `<p class="mode-hint">${selectedCount} asset${selectedCount === 1 ? "" : "s"} selected on the Browse tab.</p>`
        : `<p class="placeholder">Nothing selected yet. Pick some assets on the Browse tab, or choose a scope above.</p>`;
    }

    const albumOptions = this.albums
      .map((a) => `<option value="${a.id}">${a.album_name} (${a.asset_count})</option>`)
      .join("");

    return `
      <div id="run-filters">
        ${
          this.mode === "album"
            ? `<label>Album
                <select id="run-album">${albumOptions}</select>
              </label>`
            : ""
        }
        ${
          this.mode === "date"
            ? `<div class="field-pair">
                <label>From
                  <input id="run-date-from" type="date" />
                </label>
                <label>To
                  <input id="run-date-to" type="date" />
                </label>
              </div>`
            : ""
        }
        <label>Asset types
          <select id="run-asset-types">
            <option value="IMAGE,VIDEO">Images + Videos</option>
            <option value="IMAGE">Images only</option>
            <option value="VIDEO">Videos only</option>
          </select>
        </label>
        <label><input id="run-include-archived" type="checkbox" /> Include archived</label>
        <label><input id="run-include-deleted" type="checkbox" /> Include deleted</label>
        <label>Max assets (optional)
          <input id="run-max-assets" type="number" min="1" placeholder="unlimited" />
        </label>
      </div>
    `;
  }

  async startRun() {
    const statusEl = this.configEl.querySelector("#start-run-status");

    const body = {
      dry_run: this.configEl.querySelector("#run-dry-run").checked,
    };
    const concurrency = this.configEl.querySelector("#run-concurrency").value;
    if (concurrency) body.concurrency = parseInt(concurrency, 10);

    if (this.mode === "selection") {
      const ids = assetBrowser ? [...assetBrowser.selected] : [];
      if (ids.length === 0) {
        statusEl.textContent = "Nothing selected.";
        statusEl.className = "status-error";
        return;
      }
      body.asset_ids = ids;
    } else {
      body.asset_types = this.configEl.querySelector("#run-asset-types").value;
      body.include_archived = this.configEl.querySelector("#run-include-archived").checked;
      body.include_deleted = this.configEl.querySelector("#run-include-deleted").checked;
      const maxAssets = this.configEl.querySelector("#run-max-assets").value;
      if (maxAssets) body.max_assets = parseInt(maxAssets, 10);

      if (this.mode === "album") {
        const albumId = this.configEl.querySelector("#run-album").value;
        if (!albumId) {
          statusEl.textContent = "Pick an album.";
          statusEl.className = "status-error";
          return;
        }
        body.album_id = albumId;
      } else if (this.mode === "date") {
        const from = this.configEl.querySelector("#run-date-from").value;
        const to = this.configEl.querySelector("#run-date-to").value;
        if (!from && !to) {
          statusEl.textContent = "Pick at least one date.";
          statusEl.className = "status-error";
          return;
        }
        if (from) body.taken_after = `${from}T00:00:00.000Z`;
        if (to) body.taken_before = `${to}T23:59:59.999Z`;
      }
    }

    statusEl.textContent = "Starting…";
    statusEl.className = "";
    try {
      const run = await api.post("/runs", body);
      this.configEl.style.display = "none";
      this.activeEl.style.display = "block";
      this.activeRun.root = this.activeEl;
      await this.activeRun.show(run.id);
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status-error";
    }
  }
}
