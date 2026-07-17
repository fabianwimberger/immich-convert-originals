let assetBrowser = null;
let settingsPanel = null;
let runPanel = null;
let activeRun = null;

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  settingsPanel = new SettingsPanel(document.getElementById("tab-settings"));
  assetBrowser = new AssetBrowser(document.getElementById("tab-browse"));
  activeRun = new ActiveRun(document.getElementById("tab-convert"));
  runPanel = new RunPanel(document.getElementById("tab-convert"), activeRun);

  await settingsPanel.init();
  await assetBrowser.init();
  runPanel.init();
});
