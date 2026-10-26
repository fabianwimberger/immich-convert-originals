/** Browse/filter the Immich library, with thumbnails and multi-select. */
class AssetBrowser {
  constructor(root) {
    this.root = root;
    this.page = 1;
    this.pageSize = 120;
    this.items = [];
    this.hasMore = false;
    this.selected = new Set();
    this.lastIndex = null;
    this.albums = [];
    this.configured = false;
  }

  async init() {
    try {
      const albumResp = await api.get("/albums");
      this.albums = albumResp.items;
      this.configured = true;
    } catch (err) {
      if (err.status === 424) {
        this.configured = false;
        this.renderNotConfigured();
        return;
      }
      this.albums = [];
      this.configured = true;
    }
    this.renderShell();
    await this.search(1);
  }

  /** Called when the Browse tab is (re-)shown; retries once Immich is configured. */
  async refresh() {
    if (!this.configured) {
      await this.init();
    }
  }

  renderNotConfigured() {
    this.root.innerHTML = `
      <section class="panel">
        <div class="empty">
          <p>Connect to Immich before browsing your library.</p>
          <button id="btn-goto-settings" class="btn" type="button">Open settings</button>
        </div>
      </section>
    `;
    this.root
      .querySelector("#btn-goto-settings")
      .addEventListener("click", () => switchTab("settings"));
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
      <div class="toolbar">
        <label class="visually-hidden" for="filter-type">Asset type</label>
        <select id="filter-type" class="select">
          <option value="IMAGE">Images</option>
          <option value="VIDEO">Videos</option>
        </select>
        <label class="visually-hidden" for="filter-album">Album</label>
        <select id="filter-album" class="select">
          <option value="">All albums</option>
          ${albumOptions}
        </select>
        <label class="check"><input id="filter-archived" type="checkbox" /> Archived</label>
        <label class="check"><input id="filter-deleted" type="checkbox" /> Deleted</label>
        <button id="btn-refresh" class="btn btn--quiet btn--small" type="button">Search</button>
        <span id="selection-count" class="table-count end">0 selected</span>
      </div>
      <div class="toolbar">
        <button id="btn-select-page" class="btn btn--quiet btn--small" type="button">Select page</button>
        <button id="btn-clear-selection" class="btn btn--text btn--small" type="button">Clear selection</button>
      </div>
      <div id="asset-grid" class="asset-grid"></div>
      <div class="pager">
        <button id="btn-prev" class="btn btn--quiet btn--small" type="button" disabled>Previous</button>
        <span id="page-label" class="small">Page 1</span>
        <button id="btn-next" class="btn btn--quiet btn--small" type="button" disabled>Next</button>
        <label class="small" for="page-size">Per page</label>
        <select id="page-size" class="select">
          <option value="60">60</option>
          <option value="120" selected>120</option>
          <option value="250">250</option>
          <option value="500">500</option>
          <option value="1000">1000</option>
        </select>
      </div>
    `;

    this.root.querySelector("#btn-refresh").addEventListener("click", () => this.search(1));
    this.root.querySelector("#filter-type").addEventListener("change", () => this.search(1));
    this.root.querySelector("#filter-album").addEventListener("change", () => this.search(1));
    this.root.querySelector("#btn-prev").addEventListener("click", () => this.search(this.page - 1));
    this.root.querySelector("#btn-next").addEventListener("click", () => this.search(this.page + 1));
    this.root.querySelector("#btn-select-page").addEventListener("click", () => this.selectPage());
    this.root.querySelector("#btn-clear-selection").addEventListener("click", () => this.clearSelection());
    this.root.querySelector("#page-size").addEventListener("change", (e) => {
      this.pageSize = parseInt(e.target.value, 10);
      this.search(1);
    });
  }

  async search(page) {
    const grid = this.root.querySelector("#asset-grid");
    grid.innerHTML = `<p class="empty">Loading…</p>`;

    const filters = this.currentFilters();
    const params = new URLSearchParams({
      asset_type: filters.asset_type,
      page: String(page),
      size: String(this.pageSize),
      include_archived: String(filters.include_archived),
      include_deleted: String(filters.include_deleted),
    });
    if (filters.album_id) params.set("album_id", filters.album_id);

    try {
      const result = await api.get(`/assets?${params.toString()}`);
      this.page = result.page;
      this.items = result.items;
      this.hasMore = result.has_more;
      this.lastIndex = null;
      this.renderGrid();
      this.updatePager();
      this.updateHeadNote();
    } catch (err) {
      grid.innerHTML = `
        <p class="empty grid-message">
          <span class="status status--fail">Could not load the library</span>
          <span class="error-detail">${err.message}</span>
        </p>
      `;
    }
  }

  renderGrid() {
    const grid = this.root.querySelector("#asset-grid");
    if (this.items.length === 0) {
      grid.innerHTML = `<p class="empty">No assets match these filters.</p>`;
      return;
    }
    grid.innerHTML = this.items
      .map((asset) => {
        const isSelected = this.selected.has(asset.id);
        const checked = isSelected ? "checked" : "";
        const selectedClass = isSelected ? " selected" : "";
        const flag = asset.already_jxl ? `<span class="asset-flag">JXL</span>` : "";
        const meta = [formatOf(asset), shortDate(asset.file_created_at)]
          .filter(Boolean)
          .map((part) => `<span>${part}</span>`)
          .join("");
        return `
          <label class="asset-tile${selectedClass}" data-id="${asset.id}">
            <input type="checkbox" class="asset-select" data-id="${asset.id}" ${checked} />
            <img loading="lazy" decoding="async" src="/api/assets/${asset.id}/thumbnail" alt="${asset.original_file_name}" />
            ${flag}
            <span class="asset-name" title="${asset.original_file_name}">${asset.original_file_name}</span>
            <span class="asset-meta">${meta}</span>
          </label>
        `;
      })
      .join("");

    grid.querySelectorAll(".asset-tile").forEach((tile, index) => {
      tile.addEventListener("click", (e) => this.onTileClick(e, index));
    });
    this.schedulePrefetch();
  }

  schedulePrefetch() {
    // Warm the browser cache during idle time so scrolling never waits on
    // demand fetches. Stays to 2 parallel requests and pauses while the
    // user scrolls, so visible tiles always win the connection pool.
    this._prefetchToken = (this._prefetchToken || 0) + 1;
    const token = this._prefetchToken;
    this._lastScrollAt = 0;
    const scroller = this.root.closest(".work__main") || window;
    if (this._prefetchScrollOff) this._prefetchScrollOff();
    const onScroll = () => {
      this._lastScrollAt = Date.now();
    };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    this._prefetchScrollOff = () => scroller.removeEventListener("scroll", onScroll);
    const queue = [...this.root.querySelectorAll("#asset-grid img")]
      .filter((im) => !im.complete)
      .map((im) => im.getAttribute("src"));
    const pump = () => {
      if (token !== this._prefetchToken || document.hidden) return;
      if (Date.now() - this._lastScrollAt < 2000) {
        setTimeout(pump, 500);
        return;
      }
      const batch = [];
      const pending = new Set(
        [...this.root.querySelectorAll("#asset-grid img")]
          .filter((im) => !im.complete)
          .map((im) => im.getAttribute("src"))
      );
      while (queue.length > 0 && batch.length < 2) {
        const src = queue.shift();
        if (pending.has(src)) batch.push(src);
      }
      if (batch.length === 0) return;
      Promise.allSettled(batch.map((src) => fetch(src))).then(() => {
        if ("requestIdleCallback" in window) requestIdleCallback(pump, { timeout: 2000 });
        else setTimeout(pump, 500);
      });
    };
    if ("requestIdleCallback" in window) requestIdleCallback(pump, { timeout: 2000 });
    else setTimeout(pump, 500);
  }

  onTileClick(event, index) {
    // Take over from the label so shift-click selects a range. Updates the
    // affected tiles in place: rebuilding the whole grid per click janks
    // scrolling on large pages.
    event.preventDefault();
    const id = this.items[index].id;
    const next = !this.selected.has(id);
    let indices;
    if (event.shiftKey && this.lastIndex !== null && this.lastIndex !== index) {
      const from = Math.min(this.lastIndex, index);
      const to = Math.max(this.lastIndex, index);
      indices = [];
      for (let i = from; i <= to; i++) indices.push(i);
    } else {
      indices = [index];
    }
    const grid = this.root.querySelector("#asset-grid");
    for (const i of indices) {
      const itemId = this.items[i].id;
      if (next) this.selected.add(itemId);
      else this.selected.delete(itemId);
      const tile = grid.children[i];
      if (tile) {
        tile.classList.toggle("selected", next);
        const box = tile.querySelector(".asset-select");
        if (box) box.checked = next;
      }
    }
    this.lastIndex = index;
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
    if (window.refreshShell) window.refreshShell();
  }

  updatePager() {
    this.root.querySelector("#page-label").textContent = `Page ${this.page}`;
    this.root.querySelector("#btn-prev").disabled = this.page <= 1;
    this.root.querySelector("#btn-next").disabled = !this.hasMore;
  }

  updateHeadNote() {
    const note = document.getElementById("head-note");
    if (!note) return;
    note.textContent = `${this.items.length} assets · page ${this.page}`;
  }
}
