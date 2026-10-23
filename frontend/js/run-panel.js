/** Configure and start a run: whole library, one album, a date range, or a browser selection. */
class RunPanel {
  constructor(root, activeRun) {
    this.root = root;
    this.activeRun = activeRun;
    this.configEl = null;
    this.activeEl = null;
    this.sideEl = null;
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

  setSide(el) {
    this.sideEl = el;
  }

  isShowingActive() {
    return !!this.activeEl && this.activeEl.style.display !== "none";
  }

  /** Called when the Convert tab is (re-)shown, so the selection count and
   * album list stay current without clobbering a mode the user already chose. */
  async refresh() {
    if (this.configEl && this.configEl.style.display !== "none") {
      try {
        const resp = await api.get("/albums");
        this.albums = resp.items;
      } catch (err) {
        this.albums = [];
      }
      this.renderConfig();
      this.renderSide();
    }
  }

  showConfig() {
    this.configEl.style.display = "block";
    this.activeEl.style.display = "none";
    this.renderConfig();
    this.renderSide();
    if (window.syncSide) window.syncSide();
  }

  showActive() {
    this.configEl.style.display = "none";
    this.activeEl.style.display = "block";
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
      { id: "selection", label: "Selection" },
    ];
    const modeButtons = modes
      .map(
        (m) =>
          `<button type="button" class="mode-btn" data-mode="${m.id}" aria-pressed="${this.mode === m.id}">${m.label}</button>`
      )
      .join("");

    this.configEl.innerHTML = `
      <div class="toolbar">
        <div class="seg" role="group" aria-label="Scope">${modeButtons}</div>
      </div>
      <section class="panel">
        <div class="panel__head">
          <h2 class="h4">Scope</h2>
          <span class="small muted">${this._scopeNote(selectedCount)}</span>
        </div>
        <div class="form form--narrow">${this._renderModeBody(selectedCount)}</div>
      </section>
      ${this._renderDefaults()}
    `;

    this.configEl.querySelectorAll(".mode-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        this.mode = btn.dataset.mode;
        this.renderConfig();
        this.renderSide();
      })
    );
  }

  _renderDefaults() {
    const s = settingsPanel && settingsPanel.settings;
    if (!s) return "";
    const format = (typeof TARGET_FORMATS !== "undefined" && TARGET_FORMATS[s.image_target_format]) || s.image_target_format;
    const output = s.output_mode === "local" ? "Local files" : "Upload to Immich";
    return `
      <section class="panel">
        <div class="panel__head">
          <h2 class="h4">Defaults</h2>
          <span class="small muted">From Settings</span>
        </div>
        <dl class="pairs pairs--narrow">
          <div class="pair"><dt>Images</dt><dd>${format}</dd></div>
          <div class="pair"><dt>Videos</dt><dd>AV1</dd></div>
          <div class="pair"><dt>Output</dt><dd>${output}</dd></div>
          <div class="pair"><dt>Retry if larger</dt><dd>${s.enable_retry ? "On" : "Off"}</dd></div>
          <div class="pair"><dt>Concurrency</dt><dd>${s.concurrency}</dd></div>
        </dl>
      </section>
    `;
  }

  _scopeNote(selectedCount) {
    if (this.mode === "selection") return `${selectedCount} selected`;
    return {
      library: "Everything the filters allow",
      album: "One album",
      date: "A date range",
    }[this.mode];
  }

  _renderModeBody(selectedCount) {
    if (this.mode === "selection") {
      return selectedCount
        ? `<p class="muted">${selectedCount} asset${selectedCount === 1 ? "" : "s"} selected on the Browse tab.</p>
           <p class="field__hint">Anything already converted is skipped by the backend.</p>`
        : `<p class="empty">Nothing selected yet. Pick assets on the Browse tab, or choose another scope.</p>`;
    }

    const albumOptions = this.albums
      .map((a) => `<option value="${a.id}">${a.album_name} (${a.asset_count})</option>`)
      .join("");

    const defaults = (settingsPanel && settingsPanel.settings) || {};
    const defaultTypes = defaults.asset_types || "IMAGE,VIDEO";
    const defaultArchived = !!defaults.include_archived;
    const defaultDeleted = !!defaults.include_deleted;

    return `
      ${
        this.mode === "album"
          ? `<div class="field">
              <label class="label" for="run-album">Album</label>
              <select id="run-album" class="select">${albumOptions}</select>
            </div>`
          : ""
      }
      ${
        this.mode === "date"
          ? `<div class="cluster">
              <div class="field">
                <label class="label" for="run-date-from">From</label>
                <input id="run-date-from" class="input" type="date" />
              </div>
              <div class="field">
                <label class="label" for="run-date-to">To</label>
                <input id="run-date-to" class="input" type="date" />
              </div>
            </div>`
          : ""
      }
      <div class="field">
        <label class="label" for="run-asset-types">Asset types</label>
        <select id="run-asset-types" class="select">
          <option value="IMAGE,VIDEO" ${defaultTypes === "IMAGE,VIDEO" ? "selected" : ""}>Images and videos</option>
          <option value="IMAGE" ${defaultTypes === "IMAGE" ? "selected" : ""}>Images only</option>
          <option value="VIDEO" ${defaultTypes === "VIDEO" ? "selected" : ""}>Videos only</option>
        </select>
      </div>
      <label class="check"><input id="run-include-archived" type="checkbox" ${defaultArchived ? "checked" : ""} /> Include archived</label>
      <label class="check"><input id="run-include-deleted" type="checkbox" ${defaultDeleted ? "checked" : ""} /> Include deleted</label>
      <div class="field">
        <label class="label" for="run-max-assets">Max assets</label>
        <input id="run-max-assets" class="input" type="number" min="1" placeholder="Unlimited" />
      </div>
    `;
  }

  renderSide() {
    if (!this.sideEl) return;
    const selectedCount = assetBrowser ? assetBrowser.selected.size : 0;
    const scope = {
      library: "Every asset the filters on the left allow.",
      album: "The album picked on the left.",
      date: "Assets captured in the range on the left.",
      selection: `${selectedCount} asset${selectedCount === 1 ? "" : "s"} picked on Browse.`,
    }[this.mode];

    this.sideEl.innerHTML = `
      <div class="side__scroll">
        <div class="field">
          <span class="h4">Run</span>
          <p class="muted">${scope}</p>
        </div>
        <div class="field">
          <label class="check"><input id="run-dry-run" type="checkbox" checked /> Dry run, preview only</label>
          <p class="field__hint">Lists what would change and leaves Immich untouched.</p>
        </div>
        <div class="field">
          <label class="label" for="run-concurrency">Concurrency</label>
          <input id="run-concurrency" class="input" type="number" min="1" max="32" placeholder="Use the default" />
          <p class="field__hint">How many assets are downloaded, transcoded and uploaded in parallel.</p>
        </div>
      </div>
      <div class="side__foot">
        <button id="btn-start-run" class="btn" type="button">Start dry run</button>
        <p id="start-run-status"></p>
      </div>
    `;

    const dryRun = this.sideEl.querySelector("#run-dry-run");
    const startBtn = this.sideEl.querySelector("#btn-start-run");
    dryRun.addEventListener("change", () => {
      startBtn.textContent = dryRun.checked ? "Start dry run" : "Start run";
    });
    startBtn.addEventListener("click", () => this.startRun());
  }

  async startRun() {
    const statusEl = this.sideEl.querySelector("#start-run-status");

    const body = {
      dry_run: this.sideEl.querySelector("#run-dry-run").checked,
    };
    const concurrency = this.sideEl.querySelector("#run-concurrency").value;
    if (concurrency) body.concurrency = parseInt(concurrency, 10);

    if (this.mode === "selection") {
      const ids = assetBrowser ? [...assetBrowser.selected] : [];
      if (ids.length === 0) {
        statusEl.textContent = "Nothing selected.";
        statusEl.className = "status status--fail";
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
          statusEl.className = "status status--fail";
          return;
        }
        body.album_id = albumId;
      } else if (this.mode === "date") {
        const from = this.configEl.querySelector("#run-date-from").value;
        const to = this.configEl.querySelector("#run-date-to").value;
        if (!from && !to) {
          statusEl.textContent = "Pick at least one date.";
          statusEl.className = "status status--fail";
          return;
        }
        if (from) body.taken_after = `${from}T00:00:00.000Z`;
        if (to) body.taken_before = `${to}T23:59:59.999Z`;
      }
    }

    statusEl.textContent = "Starting…";
    statusEl.className = "status status--run";
    try {
      const run = await api.post("/runs", body);
      this.showActive();
      if (window.syncSide) window.syncSide();
      this.activeRun.root = this.activeEl;
      await this.activeRun.show(run.id);
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status status--fail";
    }
  }
}
