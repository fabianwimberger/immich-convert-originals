let assetBrowser = null;
let settingsPanel = null;
let runPanel = null;
let activeRun = null;
let runHistory = null;
let liveStrip = null;
let currentTab = "browse";

const VIEW_TITLES = {
  browse: "Browse",
  convert: "Convert",
  history: "History",
  settings: "Settings",
};

const TARGET_FORMATS = {
  jxl: "JPEG XL",
  heic: "HEIC",
  avif: "AVIF",
};

function viewNote(name) {
  if (name === "browse" && assetBrowser && assetBrowser.items.length > 0) {
    return `${assetBrowser.items.length} assets · page ${assetBrowser.page}`;
  }
  return {
    browse: "Immich library",
    convert: "Scope and run options",
    history: "Past runs",
    settings: "Connection and defaults",
  }[name];
}

/** Space saved by real runs; dry runs record would-be sizes and do not count. */
function totalSaved() {
  if (!runHistory) return 0;
  return runHistory.runs.reduce((sum, run) => {
    if (run.dry_run || run.status !== "completed") return sum;
    return sum + Math.max(0, run.input_bytes - run.output_bytes);
  }, 0);
}

function isConfigured() {
  const s = settingsPanel && settingsPanel.settings;
  return !!(s && s.immich_api_base && s.immich_api_key_set);
}

function updateStatusbar() {
  const s = settingsPanel && settingsPanel.settings;
  let host = "Not set";
  if (s && s.immich_api_base) {
    try {
      host = new URL(s.immich_api_base).host;
    } catch (err) {
      host = s.immich_api_base;
    }
  }
  const mode = s ? (s.output_mode === "local" ? "Local files" : "Upload to Immich") : "—";

  document.getElementById("statusbar").innerHTML = `
    <span><b>Immich</b> ${host}</span>
    <span>${isConfigured() ? '<span class="status status--ok">Configured</span>' : '<span class="status status--warn">Not configured</span>'}</span>
    <span>Output <b>${mode}</b></span>
    <span class="grow">Recent savings <b class="num">${fmtBytes(totalSaved())}</b></span>
  `;

  document.getElementById("head-status").innerHTML = isConfigured()
    ? '<span class="status status--ok">Configured</span>'
    : '<span class="status status--warn">Not configured</span>';
}

function renderBrowseSide(side) {
  const s = settingsPanel && settingsPanel.settings;
  const selected = assetBrowser ? assetBrowser.selected.size : 0;
  const format = s ? TARGET_FORMATS[s.image_target_format] || s.image_target_format : "—";
  const label = selected
    ? `Convert ${selected} file${selected === 1 ? "" : "s"}`
    : "Convert library";

  side.innerHTML = `
    <div class="side__scroll">
      <div class="field">
        <span class="h4">Target format</span>
        <p class="field__hint">Follows the setting; changed on the Settings tab.</p>
      </div>
      <dl class="pairs">
        <div class="pair"><dt>Images</dt><dd>${format}</dd></div>
        <div class="pair"><dt>Videos</dt><dd>AV1</dd></div>
        <div class="pair"><dt>Selected</dt><dd>${selected}</dd></div>
        <div class="pair"><dt>Saved in recent runs</dt><dd>${fmtBytes(totalSaved())}</dd></div>
      </dl>
    </div>
    <div class="side__foot">
      <button id="btn-convert-selection" class="btn" type="button">${label}</button>
    </div>
  `;

  side.querySelector("#btn-convert-selection").addEventListener("click", () => {
    const count = assetBrowser ? assetBrowser.selected.size : 0;
    runPanel.mode = count ? "selection" : "library";
    runPanel.renderConfig();
    switchTab("convert");
  });
}

function renderSide() {
  const side = document.getElementById("side-panel");
  const work = document.querySelector(".work");
  if (runPanel) runPanel.setSide(null);

  if (currentTab === "browse") {
    if (assetBrowser && assetBrowser.configured === false) {
      work.classList.add("work--full");
      side.innerHTML = "";
      return;
    }
    work.classList.remove("work--full");
    renderBrowseSide(side);
    return;
  }

  if (currentTab === "convert" && runPanel && !runPanel.isShowingActive()) {
    work.classList.remove("work--full");
    runPanel.setSide(side);
    runPanel.renderSide();
    return;
  }

  work.classList.add("work--full");
  side.innerHTML = "";
}

window.syncSide = renderSide;

window.refreshShell = () => {
  updateStatusbar();
  if (currentTab === "browse") renderSide();
};

function switchTab(name) {
  currentTab = name;
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const on = btn.dataset.tab === name;
    btn.classList.toggle("active", on);
    if (on) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
  document.getElementById("view-title").textContent = VIEW_TITLES[name];
  document.getElementById("head-note").textContent = viewNote(name);
  renderSide();
}

window.switchToActiveRun = async (runId) => {
  switchTab("convert");
  runPanel.showActive();
  renderSide();
  activeRun.root = runPanel.activeEl;
  await activeRun.show(runId);
};

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      if (btn.dataset.tab === "history" && runHistory) runHistory.refresh();
      if (btn.dataset.tab === "convert" && runPanel) runPanel.refresh();
      if (btn.dataset.tab === "browse" && assetBrowser) assetBrowser.refresh();
    });
  });

  settingsPanel = new SettingsPanel(document.getElementById("tab-settings"));
  assetBrowser = new AssetBrowser(document.getElementById("tab-browse"));
  activeRun = new ActiveRun(document.getElementById("tab-convert"));
  runPanel = new RunPanel(document.getElementById("tab-convert"), activeRun);
  runHistory = new RunHistory(document.getElementById("tab-history"));
  liveStrip = new LiveStrip(document.getElementById("live-strip"));
  window.liveStrip = liveStrip;

  await settingsPanel.init();
  await assetBrowser.init();
  runPanel.init();
  await runHistory.init();
  await liveStrip.init();

  renderSide();
  updateStatusbar();
});
