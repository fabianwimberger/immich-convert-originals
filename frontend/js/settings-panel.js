/** Immich connection + default encoding settings. */
class SettingsPanel {
  constructor(root) {
    this.root = root;
    this.settings = null;
  }

  async init() {
    await this.load();
    this.render();
  }

  async load() {
    this.settings = await api.get("/settings");
  }

  render() {
    const s = this.settings;
    this.root.innerHTML = `
      <section class="panel">
        <h2>Connection</h2>
        <label>API Base URL
          <input id="set-api-base" type="text" value="${s.immich_api_base}" placeholder="https://photos.example.com/api" />
        </label>
        <label>API Key
          <input id="set-api-key" type="password" placeholder="${s.immich_api_key_set ? "•••••••• (set)" : "not set"}" />
        </label>
        <div class="row">
          <button id="btn-test-connection">Test Connection</button>
          <button id="btn-save-connection" class="primary">Save</button>
          <span id="connection-status"></span>
        </div>
      </section>

      <section class="panel">
        <h2>Filters</h2>
        <label>Asset types
          <select id="set-asset-types">
            <option value="IMAGE,VIDEO" ${s.asset_types === "IMAGE,VIDEO" ? "selected" : ""}>Images + Videos</option>
            <option value="IMAGE" ${s.asset_types === "IMAGE" ? "selected" : ""}>Images only</option>
            <option value="VIDEO" ${s.asset_types === "VIDEO" ? "selected" : ""}>Videos only</option>
          </select>
          ${fieldHint("asset_types")}
        </label>
        <label><input id="set-include-archived" type="checkbox" ${s.include_archived ? "checked" : ""} /> Include archived assets</label>
        ${fieldHint("include_archived")}
        <label><input id="set-include-deleted" type="checkbox" ${s.include_deleted ? "checked" : ""} /> Include deleted assets</label>
        ${fieldHint("include_deleted")}
        <label>Image formats to convert</label>
        <div class="checkbox-group" id="set-convert-formats">
          ${renderFormatCheckboxes("set-fmt", s.convert_image_formats)}
        </div>
        ${fieldHint("convert_image_formats")}
        <div class="row">
          <button id="btn-save-filters" class="primary">Save</button>
          <span id="filters-status"></span>
        </div>
      </section>

      <section class="panel">
        <h2>Images</h2>
        <label>Distance (JXL, 0-25)
          <input id="set-image-distance" type="number" step="0.1" min="0" max="25" value="${s.image_distance}" />
          ${fieldHint("image_distance")}
        </label>
        <label>Distance on retry
          <input id="set-image-distance-retry" type="number" step="0.1" min="0" max="25" value="${s.image_distance_retry}" />
          ${fieldHint("image_distance_retry")}
        </label>
        <div class="row">
          <button id="btn-save-images" class="primary">Save</button>
          <span id="images-status"></span>
        </div>
      </section>

      <section class="panel">
        <h2>Videos</h2>
        <label>CRF (0-63, lower=better)
          <input id="set-video-crf" type="number" min="0" max="63" value="${s.video_crf}" />
          ${fieldHint("video_crf")}
        </label>
        <label>CRF on retry
          <input id="set-video-crf-retry" type="number" min="0" max="63" value="${s.video_crf_retry}" />
          ${fieldHint("video_crf_retry")}
        </label>
        <label>Preset (0-13, lower=slower)
          <input id="set-video-preset" type="number" min="0" max="13" value="${s.video_preset}" />
          ${fieldHint("video_preset")}
        </label>
        <label>Max dimension in pixels, short side (0=disabled)
          <input id="set-video-max-dimension" type="number" min="0" placeholder="e.g. 1080" value="${s.video_max_dimension}" />
          ${fieldHint("video_max_dimension")}
        </label>
        <label>Audio bitrate
          <input id="set-video-audio-bitrate" type="text" placeholder="e.g. 64k" value="${s.video_audio_bitrate}" />
          ${fieldHint("video_audio_bitrate")}
        </label>
        <div class="row">
          <button id="btn-save-videos" class="primary">Save</button>
          <span id="videos-status"></span>
        </div>
      </section>

      <section class="panel">
        <h2>Safety &amp; Retry</h2>
        <label><input id="set-enable-retry" type="checkbox" ${s.enable_retry ? "checked" : ""} /> Retry with more compression if output is larger</label>
        ${fieldHint("enable_retry")}
        <label><input id="set-accept-retry-output" type="checkbox" ${s.accept_retry_output ? "checked" : ""} /> Accept retry output even if still larger</label>
        ${fieldHint("accept_retry_output")}
        <label><input id="set-allow-larger" type="checkbox" ${s.allow_larger ? "checked" : ""} /> Allow larger output without retry</label>
        ${fieldHint("allow_larger")}
        <label>Concurrency
          <input id="set-concurrency" type="number" min="1" max="32" value="${s.concurrency}" />
          ${fieldHint("concurrency")}
        </label>
        <div class="row">
          <button id="btn-save-retry" class="primary">Save</button>
          <span id="retry-status"></span>
        </div>
      </section>
    `;

    this.root.querySelector("#btn-test-connection").addEventListener("click", () =>
      this.testConnection()
    );
    this.root.querySelector("#btn-save-connection").addEventListener("click", () =>
      this.saveConnection()
    );
    this.root.querySelector("#btn-save-filters").addEventListener("click", () =>
      this.saveFilters()
    );
    this.root.querySelector("#btn-save-images").addEventListener("click", () =>
      this.saveImages()
    );
    this.root.querySelector("#btn-save-videos").addEventListener("click", () =>
      this.saveVideos()
    );
    this.root.querySelector("#btn-save-retry").addEventListener("click", () =>
      this.saveRetry()
    );
  }

  async testConnection() {
    const statusEl = this.root.querySelector("#connection-status");
    statusEl.textContent = "Testing…";
    statusEl.className = "";
    const apiBase = this.root.querySelector("#set-api-base").value.trim();
    const apiKey = this.root.querySelector("#set-api-key").value.trim();
    try {
      const body = {};
      if (apiBase) body.immich_api_base = apiBase;
      if (apiKey) body.immich_api_key = apiKey;
      const result = await api.post("/settings/test-connection", body);
      statusEl.textContent = result.ok
        ? `Connected (Immich v${result.server_version})`
        : `Failed: ${result.error}`;
      statusEl.className = result.ok ? "status-ok" : "status-error";
    } catch (err) {
      statusEl.textContent = `Error: ${err.message}`;
      statusEl.className = "status-error";
    }
  }

  async _save(statusElId, body) {
    const statusEl = this.root.querySelector(`#${statusElId}`);
    try {
      this.settings = await api.put("/settings", body);
      this.render();
      const el = this.root.querySelector(`#${statusElId}`);
      el.textContent = "Saved";
      el.className = "status-ok";
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status-error";
    }
  }

  async saveConnection() {
    const apiBase = this.root.querySelector("#set-api-base").value.trim();
    const apiKey = this.root.querySelector("#set-api-key").value.trim();
    const body = { immich_api_base: apiBase };
    if (apiKey) body.immich_api_key = apiKey;
    await this._save("connection-status", body);
  }

  async saveFilters() {
    await this._save("filters-status", {
      asset_types: this.root.querySelector("#set-asset-types").value,
      include_archived: this.root.querySelector("#set-include-archived").checked,
      include_deleted: this.root.querySelector("#set-include-deleted").checked,
      convert_image_formats: readFormatCheckboxes(this.root, "set-fmt"),
    });
  }

  async saveImages() {
    await this._save("images-status", {
      image_distance: parseFloat(this.root.querySelector("#set-image-distance").value),
      image_distance_retry: parseFloat(
        this.root.querySelector("#set-image-distance-retry").value
      ),
    });
  }

  async saveVideos() {
    await this._save("videos-status", {
      video_crf: parseInt(this.root.querySelector("#set-video-crf").value, 10),
      video_crf_retry: parseInt(
        this.root.querySelector("#set-video-crf-retry").value,
        10
      ),
      video_preset: parseInt(this.root.querySelector("#set-video-preset").value, 10),
      video_max_dimension: parseInt(
        this.root.querySelector("#set-video-max-dimension").value,
        10
      ),
      video_audio_bitrate: this.root
        .querySelector("#set-video-audio-bitrate")
        .value.trim(),
    });
  }

  async saveRetry() {
    await this._save("retry-status", {
      enable_retry: this.root.querySelector("#set-enable-retry").checked,
      accept_retry_output: this.root.querySelector("#set-accept-retry-output").checked,
      allow_larger: this.root.querySelector("#set-allow-larger").checked,
      concurrency: parseInt(this.root.querySelector("#set-concurrency").value, 10),
    });
  }
}
