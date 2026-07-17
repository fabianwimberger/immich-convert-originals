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
        <h2>Immich Connection</h2>
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
        <h2>Default Encoding</h2>
        <label>Asset types
          <select id="set-asset-types">
            <option value="IMAGE,VIDEO" ${s.asset_types === "IMAGE,VIDEO" ? "selected" : ""}>Images + Videos</option>
            <option value="IMAGE" ${s.asset_types === "IMAGE" ? "selected" : ""}>Images only</option>
            <option value="VIDEO" ${s.asset_types === "VIDEO" ? "selected" : ""}>Videos only</option>
          </select>
        </label>
        <label><input id="set-include-archived" type="checkbox" ${s.include_archived ? "checked" : ""} /> Include archived assets</label>
        <label><input id="set-include-deleted" type="checkbox" ${s.include_deleted ? "checked" : ""} /> Include deleted assets</label>
        <label>Image distance (JXL, 0=lossless, 1=visually lossless)
          <input id="set-image-distance" type="number" step="0.1" min="0" value="${s.image_distance}" />
        </label>
        <label>Video CRF (0-63, lower=better)
          <input id="set-video-crf" type="number" min="0" max="63" value="${s.video_crf}" />
        </label>
        <label>Video preset (0-13, lower=slower)
          <input id="set-video-preset" type="number" min="0" max="13" value="${s.video_preset}" />
        </label>
        <label>Concurrency
          <input id="set-concurrency" type="number" min="1" max="32" value="${s.concurrency}" />
        </label>
        <div class="row">
          <button id="btn-save-encoding" class="primary">Save</button>
          <span id="encoding-status"></span>
        </div>
      </section>

      <section class="panel">
        <h2>Retry &amp; Safety</h2>
        <label>Video max dimension (0=disabled)
          <input id="set-video-max-dimension" type="number" min="0" value="${s.video_max_dimension}" />
        </label>
        <label>Video audio bitrate
          <input id="set-video-audio-bitrate" type="text" value="${s.video_audio_bitrate}" />
        </label>
        <label><input id="set-enable-retry" type="checkbox" ${s.enable_retry ? "checked" : ""} /> Retry with more compression if output is larger</label>
        <label>Image distance on retry
          <input id="set-image-distance-retry" type="number" step="0.1" min="0" value="${s.image_distance_retry}" />
        </label>
        <label>Video CRF on retry
          <input id="set-video-crf-retry" type="number" min="0" max="63" value="${s.video_crf_retry}" />
        </label>
        <label><input id="set-accept-retry-output" type="checkbox" ${s.accept_retry_output ? "checked" : ""} /> Accept retry output even if still larger</label>
        <label><input id="set-allow-larger" type="checkbox" ${s.allow_larger ? "checked" : ""} /> Allow larger output without retry</label>
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
    this.root.querySelector("#btn-save-encoding").addEventListener("click", () =>
      this.saveEncoding()
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

  async saveConnection() {
    const statusEl = this.root.querySelector("#connection-status");
    const apiBase = this.root.querySelector("#set-api-base").value.trim();
    const apiKey = this.root.querySelector("#set-api-key").value.trim();
    const body = { immich_api_base: apiBase };
    if (apiKey) body.immich_api_key = apiKey;
    try {
      this.settings = await api.put("/settings", body);
      this.render();
      this.root.querySelector("#connection-status").textContent = "Saved";
      this.root.querySelector("#connection-status").className = "status-ok";
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status-error";
    }
  }

  async saveEncoding() {
    const statusEl = this.root.querySelector("#encoding-status");
    const body = {
      asset_types: this.root.querySelector("#set-asset-types").value,
      include_archived: this.root.querySelector("#set-include-archived").checked,
      include_deleted: this.root.querySelector("#set-include-deleted").checked,
      image_distance: parseFloat(this.root.querySelector("#set-image-distance").value),
      video_crf: parseInt(this.root.querySelector("#set-video-crf").value, 10),
      video_preset: parseInt(this.root.querySelector("#set-video-preset").value, 10),
      concurrency: parseInt(this.root.querySelector("#set-concurrency").value, 10),
    };
    try {
      this.settings = await api.put("/settings", body);
      statusEl.textContent = "Saved";
      statusEl.className = "status-ok";
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status-error";
    }
  }

  async saveRetry() {
    const statusEl = this.root.querySelector("#retry-status");
    const body = {
      video_max_dimension: parseInt(
        this.root.querySelector("#set-video-max-dimension").value,
        10
      ),
      video_audio_bitrate: this.root.querySelector("#set-video-audio-bitrate").value.trim(),
      enable_retry: this.root.querySelector("#set-enable-retry").checked,
      image_distance_retry: parseFloat(
        this.root.querySelector("#set-image-distance-retry").value
      ),
      video_crf_retry: parseInt(this.root.querySelector("#set-video-crf-retry").value, 10),
      accept_retry_output: this.root.querySelector("#set-accept-retry-output").checked,
      allow_larger: this.root.querySelector("#set-allow-larger").checked,
    };
    try {
      this.settings = await api.put("/settings", body);
      statusEl.textContent = "Saved";
      statusEl.className = "status-ok";
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status-error";
    }
  }
}
