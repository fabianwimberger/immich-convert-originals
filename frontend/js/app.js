let assetBrowser = null;
let settingsPanel = null;
let runPanel = null;
let activeRun = null;
let runHistory = null;

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

window.switchToActiveRun = async (runId) => {
  switchTab("convert");
  runPanel.configEl.style.display = "none";
  runPanel.activeEl.style.display = "block";
  activeRun.root = runPanel.activeEl;
  await activeRun.show(runId);
};

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      if (btn.dataset.tab === "history" && runHistory) runHistory.refresh();
    });
  });

  settingsPanel = new SettingsPanel(document.getElementById("tab-settings"));
  assetBrowser = new AssetBrowser(document.getElementById("tab-browse"));
  activeRun = new ActiveRun(document.getElementById("tab-convert"));
  runPanel = new RunPanel(document.getElementById("tab-convert"), activeRun);
  runHistory = new RunHistory(document.getElementById("tab-history"));

  await settingsPanel.init();
  await assetBrowser.init();
  runPanel.init();
  await runHistory.init();
});
