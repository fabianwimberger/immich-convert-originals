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
      <div class="settings-grid">
        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Connection</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="label" for="set-api-base">API base URL</label>
              <input id="set-api-base" class="input" type="text" value="${s.immich_api_base}" placeholder="https://photos.example.com/api" />
              ${fieldHint("immich_api_base")}
            </div>
            <div class="field">
              <label class="label" for="set-api-key">API key</label>
              <input id="set-api-key" class="input" type="password" placeholder="${s.immich_api_key_set ? "•••••••• (set)" : "Not set"}" />
            </div>
            <div class="field">
              <label class="check">
                <input id="set-allow-insecure-ssl" type="checkbox" ${s.immich_allow_insecure_ssl ? "checked" : ""} />
                Allow insecure SSL certificates (self-signed)
              </label>
              ${fieldHint("immich_allow_insecure_ssl")}
            </div>
            <div class="actions">
              <button id="btn-save-connection" class="btn btn--quiet btn--small" type="button">Save connection</button>
              <button id="btn-test-connection" class="btn btn--quiet btn--small" type="button">Test connection</button>
              <span id="connection-status"></span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Filters</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="label" for="set-asset-types">Asset types</label>
              <select id="set-asset-types" class="select">
                <option value="IMAGE,VIDEO" ${s.asset_types === "IMAGE,VIDEO" ? "selected" : ""}>Images and videos</option>
                <option value="IMAGE" ${s.asset_types === "IMAGE" ? "selected" : ""}>Images only</option>
                <option value="VIDEO" ${s.asset_types === "VIDEO" ? "selected" : ""}>Videos only</option>
              </select>
              ${fieldHint("asset_types")}
            </div>
            <div class="field">
              <label class="check"><input id="set-include-archived" type="checkbox" ${s.include_archived ? "checked" : ""} /> Include archived assets</label>
              ${fieldHint("include_archived")}
            </div>
            <div class="field">
              <label class="check"><input id="set-include-deleted" type="checkbox" ${s.include_deleted ? "checked" : ""} /> Include deleted assets</label>
              ${fieldHint("include_deleted")}
            </div>
            <div class="field">
              <span class="label">Image formats to convert</span>
              <div class="checkbox-group" id="set-convert-formats">
                ${renderFormatCheckboxes("set-fmt", s.convert_image_formats)}
              </div>
              ${fieldHint("convert_image_formats")}
            </div>
            <div class="actions">
              <button id="btn-save-filters" class="btn btn--quiet btn--small" type="button">Save filters</button>
              <span id="filters-status"></span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Images</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="label" for="set-image-target-format">Target format</label>
              <select id="set-image-target-format" class="select">
                <option value="jxl" ${s.image_target_format === "jxl" ? "selected" : ""}>JPEG XL (JXL)</option>
                <option value="heic" ${s.image_target_format === "heic" ? "selected" : ""}>HEIC</option>
                <option value="avif" ${s.image_target_format === "avif" ? "selected" : ""}>AVIF</option>
              </select>
              ${fieldHint("image_target_format")}
            </div>
            <div class="format-fields form" data-format="jxl" style="${s.image_target_format === "jxl" ? "" : "display:none"}">
              <div class="field">
                <label class="label" for="set-image-distance">Distance (0-25)</label>
                <input id="set-image-distance" class="input" type="number" step="0.1" min="0" max="25" value="${s.image_distance}" />
                ${fieldHint("image_distance")}
              </div>
              <div class="field">
                <label class="label" for="set-image-distance-retry">Distance on retry</label>
                <input id="set-image-distance-retry" class="input" type="number" step="0.1" min="0" max="25" value="${s.image_distance_retry}" />
                ${fieldHint("image_distance_retry")}
              </div>
              <div class="field">
                <label class="label" for="set-image-jxl-effort">JXL encoder effort (1-10)</label>
                <input id="set-image-jxl-effort" class="input" type="number" step="1" min="1" max="10" value="${s.image_jxl_effort}" />
                ${fieldHint("image_jxl_effort")}
              </div>
            </div>
            <div class="format-fields form" data-format="heic" style="${s.image_target_format === "heic" ? "" : "display:none"}">
              <div class="field">
                <label class="label" for="set-image-quality-heic">Quality (0-100)</label>
                <input id="set-image-quality-heic" class="input" type="number" min="0" max="100" value="${s.image_quality_heic}" />
                ${fieldHint("image_quality_heic")}
              </div>
              <div class="field">
                <label class="label" for="set-image-quality-heic-retry">Quality on retry</label>
                <input id="set-image-quality-heic-retry" class="input" type="number" min="0" max="100" value="${s.image_quality_heic_retry}" />
                ${fieldHint("image_quality_heic_retry")}
              </div>
            </div>
            <div class="format-fields form" data-format="avif" style="${s.image_target_format === "avif" ? "" : "display:none"}">
              <div class="field">
                <label class="label" for="set-image-quality-avif">Quality (0-100)</label>
                <input id="set-image-quality-avif" class="input" type="number" min="0" max="100" value="${s.image_quality_avif}" />
                ${fieldHint("image_quality_avif")}
              </div>
              <div class="field">
                <label class="label" for="set-image-quality-avif-retry">Quality on retry</label>
                <input id="set-image-quality-avif-retry" class="input" type="number" min="0" max="100" value="${s.image_quality_avif_retry}" />
                ${fieldHint("image_quality_avif_retry")}
              </div>
            </div>
            <div class="actions">
              <button id="btn-save-images" class="btn btn--quiet btn--small" type="button">Save image settings</button>
              <span id="images-status"></span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Videos</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="label" for="set-video-crf">CRF (0-63, lower is better)</label>
              <input id="set-video-crf" class="input" type="number" min="0" max="63" value="${s.video_crf}" />
              ${fieldHint("video_crf")}
            </div>
            <div class="field">
              <label class="label" for="set-video-crf-retry">CRF on retry</label>
              <input id="set-video-crf-retry" class="input" type="number" min="0" max="63" value="${s.video_crf_retry}" />
              ${fieldHint("video_crf_retry")}
            </div>
            <div class="field">
              <label class="label" for="set-video-preset">Preset (0-13, lower is slower)</label>
              <input id="set-video-preset" class="input" type="number" min="0" max="13" value="${s.video_preset}" />
              ${fieldHint("video_preset")}
            </div>
            <div class="field">
              <label class="label" for="set-video-max-dimension">Max dimension in pixels, short side (0 disables)</label>
              <input id="set-video-max-dimension" class="input" type="number" min="0" placeholder="e.g. 1080" value="${s.video_max_dimension}" />
              ${fieldHint("video_max_dimension")}
            </div>
            <div class="field">
              <label class="label" for="set-video-audio-bitrate">Audio bitrate</label>
              <input id="set-video-audio-bitrate" class="input" type="text" placeholder="e.g. 64k" value="${s.video_audio_bitrate}" />
              ${fieldHint("video_audio_bitrate")}
            </div>
            <div class="field">
              <label class="check"><input id="set-convert-live-photo-videos" type="checkbox" ${s.convert_live_photo_videos ? "checked" : ""} /> Convert live photo videos</label>
              ${fieldHint("convert_live_photo_videos")}
            </div>
            <div class="actions">
              <button id="btn-save-videos" class="btn btn--quiet btn--small" type="button">Save video settings</button>
              <span id="videos-status"></span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Output</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="label" for="set-output-mode">Mode</label>
              <select id="set-output-mode" class="select">
                <option value="upload" ${s.output_mode === "upload" ? "selected" : ""}>Upload to Immich</option>
                <option value="local" ${s.output_mode === "local" ? "selected" : ""}>Save locally, no upload</option>
              </select>
              ${fieldHint("output_mode")}
            </div>
            <div class="output-local-fields form" style="${s.output_mode === "local" ? "" : "display:none"}">
              <div class="field">
                <label class="label" for="set-local-output-dir">Local output directory</label>
                <input id="set-local-output-dir" class="input" type="text" placeholder="/app/output" value="${s.local_output_dir}" />
                ${fieldHint("local_output_dir")}
              </div>
              <div class="field">
                <label class="check"><input id="set-local-keep-originals" type="checkbox" ${s.local_keep_originals ? "checked" : ""} /> Keep a copy of the original alongside</label>
                ${fieldHint("local_keep_originals")}
              </div>
            </div>
            <div class="output-upload-fields form" style="${s.output_mode === "local" ? "display:none" : ""}">
              <div class="field">
                <label class="check"><input id="set-upload-external-assets" type="checkbox" ${s.upload_external_assets ? "checked" : ""} /> Convert external library assets</label>
                ${fieldHint("upload_external_assets")}
              </div>
            </div>
            <div class="actions">
              <button id="btn-save-output" class="btn btn--quiet btn--small" type="button">Save output</button>
              <span id="output-status"></span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel__head">
            <h2 class="h4">Safety and retry</h2>
          </div>
          <div class="form">
            <div class="field">
              <label class="check"><input id="set-enable-retry" type="checkbox" ${s.enable_retry ? "checked" : ""} /> Retry with more compression if output is larger</label>
              ${fieldHint("enable_retry")}
            </div>
            <div class="field">
              <label class="check"><input id="set-accept-retry-output" type="checkbox" ${s.accept_retry_output ? "checked" : ""} /> Accept retry output even if still larger</label>
              ${fieldHint("accept_retry_output")}
            </div>
            <div class="field">
              <label class="check"><input id="set-allow-larger" type="checkbox" ${s.allow_larger ? "checked" : ""} /> Allow larger output without retry</label>
              ${fieldHint("allow_larger")}
            </div>
            <div class="field">
              <label class="label" for="set-concurrency">Concurrency</label>
              <input id="set-concurrency" class="input" type="number" min="1" max="32" value="${s.concurrency}" />
              ${fieldHint("concurrency")}
            </div>
            <div class="actions">
              <button id="btn-save-retry" class="btn btn--quiet btn--small" type="button">Save safety settings</button>
              <span id="retry-status"></span>
            </div>
          </div>
        </section>
      </div>
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
    this.root
      .querySelector("#set-image-target-format")
      .addEventListener("change", (e) => {
        this.root.querySelectorAll(".format-fields").forEach((el) => {
          el.style.display = el.dataset.format === e.target.value ? "" : "none";
        });
      });
    this.root.querySelector("#btn-save-videos").addEventListener("click", () =>
      this.saveVideos()
    );
    this.root.querySelector("#btn-save-output").addEventListener("click", () =>
      this.saveOutput()
    );
    this.root.querySelector("#set-output-mode").addEventListener("change", (e) => {
      this.root.querySelector(".output-local-fields").style.display =
        e.target.value === "local" ? "" : "none";
      this.root.querySelector(".output-upload-fields").style.display =
        e.target.value === "local" ? "none" : "";
    });
    this.root.querySelector("#btn-save-retry").addEventListener("click", () =>
      this.saveRetry()
    );
  }

  async testConnection() {
    const statusEl = this.root.querySelector("#connection-status");
    statusEl.textContent = "Testing…";
    statusEl.className = "status status--run";
    const apiBase = this.root.querySelector("#set-api-base").value.trim();
    const apiKey = this.root.querySelector("#set-api-key").value.trim();
    try {
      const body = {};
      if (apiBase) body.immich_api_base = apiBase;
      if (apiKey) body.immich_api_key = apiKey;
      body.immich_allow_insecure_ssl = this.root.querySelector(
        "#set-allow-insecure-ssl"
      ).checked;
      const result = await api.post("/settings/test-connection", body);
      statusEl.textContent = result.ok
        ? `Connected, Immich v${result.server_version}`
        : `Failed: ${result.error}`;
      statusEl.className = result.ok ? "status status--ok" : "status status--fail";
    } catch (err) {
      statusEl.textContent = `Error: ${err.message}`;
      statusEl.className = "status status--fail";
    }
  }

  async _save(statusElId, body) {
    const statusEl = this.root.querySelector(`#${statusElId}`);
    try {
      this.settings = await api.put("/settings", body);
      this.render();
      const el = this.root.querySelector(`#${statusElId}`);
      el.textContent = "Saved";
      el.className = "status status--ok";
      if (window.refreshShell) window.refreshShell();
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = "status status--fail";
    }
  }

  async saveConnection() {
    const apiBase = this.root.querySelector("#set-api-base").value.trim();
    const apiKey = this.root.querySelector("#set-api-key").value.trim();
    const body = {
      immich_api_base: apiBase,
      immich_allow_insecure_ssl: this.root.querySelector(
        "#set-allow-insecure-ssl"
      ).checked,
    };
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
      image_target_format: this.root.querySelector("#set-image-target-format").value,
      image_distance: parseFloat(this.root.querySelector("#set-image-distance").value),
      image_distance_retry: parseFloat(
        this.root.querySelector("#set-image-distance-retry").value
      ),
      image_jxl_effort: parseInt(
        this.root.querySelector("#set-image-jxl-effort").value,
        10
      ),
      image_quality_heic: parseInt(
        this.root.querySelector("#set-image-quality-heic").value,
        10
      ),
      image_quality_heic_retry: parseInt(
        this.root.querySelector("#set-image-quality-heic-retry").value,
        10
      ),
      image_quality_avif: parseInt(
        this.root.querySelector("#set-image-quality-avif").value,
        10
      ),
      image_quality_avif_retry: parseInt(
        this.root.querySelector("#set-image-quality-avif-retry").value,
        10
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
      convert_live_photo_videos: this.root.querySelector(
        "#set-convert-live-photo-videos"
      ).checked,
    });
  }

  async saveOutput() {
    await this._save("output-status", {
      output_mode: this.root.querySelector("#set-output-mode").value,
      local_output_dir: this.root.querySelector("#set-local-output-dir").value.trim(),
      local_keep_originals: this.root.querySelector("#set-local-keep-originals")
        .checked,
      upload_external_assets: this.root.querySelector("#set-upload-external-assets")
        .checked,
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
