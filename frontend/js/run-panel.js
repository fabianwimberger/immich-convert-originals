/** Configure and start a run, either from filters or from a browser selection. */
class RunPanel {
  constructor(root, activeRun) {
    this.root = root;
    this.activeRun = activeRun;
    this.configEl = null;
    this.activeEl = null;
  }

  init() {
    this.root.innerHTML = `
      <div id="run-config"></div>
      <div id="run-active-container" style="display:none"></div>
    `;
    this.configEl = this.root.querySelector("#run-config");
    this.activeEl = this.root.querySelector("#run-active-container");
    this.renderConfig();
  }

  renderConfig() {
    const selectedCount = assetBrowser ? assetBrowser.selected.size : 0;
    this.configEl.style.display = "block";
    this.activeEl.style.display = "none";

    this.configEl.innerHTML = `
      <section class="panel">
        <h2>Start a Run</h2>
        <div class="row">
          <label><input type="radio" name="run-mode" value="selection" ${selectedCount ? "checked" : ""} /> From selection (${selectedCount} assets)</label>
          <label><input type="radio" name="run-mode" value="filters" ${selectedCount ? "" : "checked"} /> From filters</label>
        </div>

        <div id="run-filters">
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

    this.root.querySelectorAll('input[name="run-mode"]').forEach((el) =>
      el.addEventListener("change", () => this.updateModeVisibility())
    );
    this.updateModeVisibility();

    this.configEl
      .querySelector("#btn-start-run")
      .addEventListener("click", () => this.startRun());
  }

  updateModeVisibility() {
    const mode = this.configEl.querySelector('input[name="run-mode"]:checked').value;
    this.configEl.querySelector("#run-filters").style.display =
      mode === "filters" ? "block" : "none";
  }

  async startRun() {
    const statusEl = this.configEl.querySelector("#start-run-status");
    const mode = this.configEl.querySelector('input[name="run-mode"]:checked').value;

    const body = {
      dry_run: this.configEl.querySelector("#run-dry-run").checked,
    };

    const concurrency = this.configEl.querySelector("#run-concurrency").value;
    if (concurrency) body.concurrency = parseInt(concurrency, 10);

    if (mode === "selection") {
      const ids = assetBrowser ? [...assetBrowser.selected] : [];
      if (ids.length === 0) {
        statusEl.textContent = "No assets selected.";
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
