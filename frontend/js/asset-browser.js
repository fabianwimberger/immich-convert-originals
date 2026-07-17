/** Browse/filter the Immich library, with thumbnails and multi-select. */
class AssetBrowser {
  constructor(root) {
    this.root = root;
    this.page = 1;
    this.items = [];
    this.hasMore = false;
    this.selected = new Set();
    this.albums = [];
  }

  async init() {
    try {
      const albumResp = await api.get("/albums");
      this.albums = albumResp.items;
    } catch (err) {
      if (err.status === 424) {
        this.renderNotConfigured();
        return;
      }
      this.albums = [];
    }
    this.renderShell();
    await this.search(1);
  }

  renderNotConfigured() {
    this.root.innerHTML = `
      <section class="panel">
        <p class="placeholder">
          Connect to Immich on the Settings tab before browsing your library.
        </p>
      </section>
    `;
  }

  currentFilters() {
    return {
      asset_type: this.root.querySelector("#filter-type").value,
      album_id: this.root.querySelector("#filter-album").value || undefined,
      include_archived: this.root.querySelector("#filter-archived").checked,
      include_deleted: this.root.querySelector("#filter-deleted").checked,
    };
  }

  renderShell() {
    const albumOptions = this.albums
      .map((a) => `<option value="${a.id}">${a.album_name} (${a.asset_count})</option>`)
      .join("");

    this.root.innerHTML = `
      <section class="panel">
        <div class="row filters">
          <select id="filter-type">
            <option value="IMAGE">Images</option>
            <option value="VIDEO">Videos</option>
          </select>
          <select id="filter-album">
            <option value="">All albums</option>
            ${albumOptions}
          </select>
          <label><input id="filter-archived" type="checkbox" /> Archived</label>
          <label><input id="filter-deleted" type="checkbox" /> Deleted</label>
          <button id="btn-refresh">Search</button>
        </div>
        <div class="row selection-bar">
          <span id="selection-count">0 selected</span>
          <button id="btn-select-page">Select all on page</button>
          <button id="btn-clear-selection">Clear selection</button>
        </div>
        <div id="asset-grid" class="asset-grid"></div>
        <div class="row pager">
          <button id="btn-prev" disabled>Previous</button>
          <span id="page-label">Page 1</span>
          <button id="btn-next" disabled>Next</button>
        </div>
      </section>
    `;

    this.root.querySelector("#btn-refresh").addEventListener("click", () => this.search(1));
    this.root.querySelector("#filter-type").addEventListener("change", () => this.search(1));
    this.root.querySelector("#filter-album").addEventListener("change", () => this.search(1));
    this.root.querySelector("#btn-prev").addEventListener("click", () => this.search(this.page - 1));
    this.root.querySelector("#btn-next").addEventListener("click", () => this.search(this.page + 1));
    this.root.querySelector("#btn-select-page").addEventListener("click", () => this.selectPage());
    this.root.querySelector("#btn-clear-selection").addEventListener("click", () => this.clearSelection());
  }

  async search(page) {
    const grid = this.root.querySelector("#asset-grid");
    grid.innerHTML = `<p class="placeholder">Loading…</p>`;

    const filters = this.currentFilters();
    const params = new URLSearchParams({
      asset_type: filters.asset_type,
      page: String(page),
      size: "40",
      include_archived: String(filters.include_archived),
      include_deleted: String(filters.include_deleted),
    });
    if (filters.album_id) params.set("album_id", filters.album_id);

    try {
      const result = await api.get(`/assets?${params.toString()}`);
      this.page = result.page;
      this.items = result.items;
      this.hasMore = result.has_more;
      this.renderGrid();
      this.updatePager();
    } catch (err) {
      grid.innerHTML = `<p class="status-error">${err.message}</p>`;
    }
  }

  renderGrid() {
    const grid = this.root.querySelector("#asset-grid");
    if (this.items.length === 0) {
      grid.innerHTML = `<p class="placeholder">No assets match these filters.</p>`;
      return;
    }
    grid.innerHTML = this.items
      .map((asset) => {
        const checked = this.selected.has(asset.id) ? "checked" : "";
        const badge = asset.already_jxl ? `<span class="badge">JXL</span>` : "";
        return `
          <label class="asset-tile" data-id="${asset.id}">
            <input type="checkbox" class="asset-select" data-id="${asset.id}" ${checked} />
            <img loading="lazy" src="/api/assets/${asset.id}/thumbnail" alt="${asset.original_file_name}" />
            ${badge}
            <span class="asset-name" title="${asset.original_file_name}">${asset.original_file_name}</span>
          </label>
        `;
      })
      .join("");

    grid.querySelectorAll(".asset-select").forEach((el) => {
      el.addEventListener("change", (e) => this.toggleSelection(e.target.dataset.id, e.target.checked));
    });
  }

  toggleSelection(id, isSelected) {
    if (isSelected) this.selected.add(id);
    else this.selected.delete(id);
    this.updateSelectionCount();
  }

  selectPage() {
    this.items.forEach((a) => this.selected.add(a.id));
    this.renderGrid();
    this.updateSelectionCount();
  }

  clearSelection() {
    this.selected.clear();
    this.renderGrid();
    this.updateSelectionCount();
  }

  updateSelectionCount() {
    this.root.querySelector("#selection-count").textContent = `${this.selected.size} selected`;
  }

  updatePager() {
    this.root.querySelector("#page-label").textContent = `Page ${this.page}`;
    this.root.querySelector("#btn-prev").disabled = this.page <= 1;
    this.root.querySelector("#btn-next").disabled = !this.hasMore;
  }
}
