(() => {
  const el = (id) => document.getElementById(id);
  let allImages = [];

  // ---------- Cached renders (approved + legacy only) ----------
  async function load() {
    const grid = el("admin-grid");
    grid.innerHTML = '<div class="empty-state">Loading…</div>';
    try {
      const res = await fetch("/api/admin/images", { credentials: "include" });
      if (!res.ok) throw new Error("Could not load cached renders.");
      allImages = await res.json();
      populateFilterOptions(approvedImages());
      applyFilters();
      renderUnprocessed();
    } catch (err) {
      grid.innerHTML = `<div class="empty-state">${err.message}</div>`;
    }
  }

  function approvedImages() {
    return allImages.filter((i) => i.is_approved);
  }
  function unprocessedImages() {
    return allImages.filter((i) => !i.is_approved);
  }

  function populateFilterOptions(images) {
    const makes = [...new Set(images.map((i) => i.make).filter(Boolean))].sort();
    fillSelect("filter-make", makes, "All makes");
    refreshModelOptions(images);
    const colors = [...new Set(images.map((i) => i.color).filter(Boolean))].sort();
    fillSelect("filter-color", colors, "All colors");
    const categories = [...new Set(images.map((i) => i.category).filter(Boolean))].sort();
    fillSelect("filter-category", categories, "All types");
  }

  function refreshModelOptions(images) {
    const selectedMake = el("filter-make").value;
    const pool = selectedMake ? images.filter((i) => i.make === selectedMake) : images;
    const modelsList = [...new Set(pool.map((i) => i.model).filter(Boolean))].sort();
    const previousModel = el("filter-model").value;
    fillSelect("filter-model", modelsList, "All models");
    if (modelsList.includes(previousModel)) el("filter-model").value = previousModel;
  }

  function fillSelect(id, values, allLabel) {
    const select = el(id);
    const current = select.value;
    select.innerHTML =
      `<option value="">${allLabel}</option>` + values.map((v) => `<option value="${v}">${v}</option>`).join("");
    if (values.includes(current)) select.value = current;
  }

  function applyFilters() {
    const make = el("filter-make").value;
    const model = el("filter-model").value;
    const color = el("filter-color").value;
    const category = el("filter-category").value;
    const text = el("filter-input").value.toLowerCase();

    const filtered = approvedImages().filter((img) => {
      if (make && img.make !== make) return false;
      if (model && img.model !== model) return false;
      if (color && img.color !== color) return false;
      if (category && img.category !== category) return false;
      if (text && !img.filename.toLowerCase().includes(text)) return false;
      return true;
    });
    renderGrid("admin-grid", filtered, "No cached renders match these filters.");
  }

  el("filter-make").addEventListener("change", () => {
    refreshModelOptions(approvedImages());
    applyFilters();
  });
  ["filter-model", "filter-color", "filter-category"].forEach((id) => {
    el(id).addEventListener("change", applyFilters);
  });
  el("filter-input").addEventListener("input", applyFilters);

  function renderGrid(gridId, images, emptyMessage) {
    const grid = el(gridId);
    if (!images.length) {
      grid.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
      return;
    }
    grid.innerHTML = "";
    images.forEach((img) => {
      const card = document.createElement("div");
      card.className = "admin-card";
      const tags = [img.make, img.model, img.color, img.category].filter(Boolean).join(" · ");
      card.innerHTML = `
        <img src="${img.url}" alt="${img.filename}" loading="lazy" />
        <div class="admin-card-body">
          <div class="admin-card-name">${img.filename}</div>
          <div class="admin-card-meta">${tags || "Unrecognized"}</div>
          <div class="admin-card-meta">${img.size_kb} KB &middot; ${new Date(img.modified * 1000).toLocaleString()}</div>
          <button class="btn btn-ghost admin-delete-btn" data-filename="${img.filename}">Delete</button>
        </div>`;
      grid.appendChild(card);
    });

    grid.querySelectorAll(".admin-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteImage(btn.dataset.filename, btn));
    });
  }

  async function deleteImage(filename, btn) {
    if (!confirm(`Delete ${filename}? It'll regenerate next time it's needed.`)) return;
    btn.disabled = true;
    btn.textContent = "Deleting…";
    try {
      const res = await fetch(`/api/admin/images/${filename}`, { method: "DELETE", credentials: "include" });
      if (!res.ok) throw new Error("Delete failed.");
      await load();
      await loadPrewarmStatus();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Delete";
      alert(err.message);
    }
  }

  // ---------- Unprocessed review queue ----------
  function renderUnprocessed() {
    const pending = unprocessedImages();
    el("unprocessed-count").textContent = `${pending.length} pending`;
    const grid = el("unprocessed-grid");

    if (!pending.length) {
      grid.innerHTML = '<div class="empty-state">Nothing waiting on review right now.</div>';
      return;
    }
    grid.innerHTML = "";
    pending.forEach((img) => {
      const card = document.createElement("div");
      card.className = "admin-card unprocessed-card";
      const tags = [img.make, img.model, img.color, img.category].filter(Boolean).join(" · ");
      card.innerHTML = `
        <img src="${img.url}" alt="${img.filename}" loading="lazy" />
        <div class="admin-card-body">
          <div class="admin-card-name">${img.filename}</div>
          <div class="admin-card-meta">${tags || "Unrecognized"}</div>
          <div class="unprocessed-actions">
            <button class="btn btn-ghost approve-btn" data-filename="${img.filename}">Approve</button>
            <button class="btn btn-ghost admin-delete-btn" data-filename="${img.filename}">Delete</button>
          </div>
        </div>`;
      grid.appendChild(card);
    });

    grid.querySelectorAll(".approve-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        btn.textContent = "Approving…";
        try {
          const res = await fetch(`/api/admin/images/${btn.dataset.filename}/approve`, {
            method: "POST",
            credentials: "include",
          });
          if (!res.ok) throw new Error("Approve failed.");
          await load();
        } catch (err) {
          btn.disabled = false;
          btn.textContent = "Approve";
          alert(err.message);
        }
      });
    });
    grid.querySelectorAll(".unprocessed-card .admin-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteImage(btn.dataset.filename, btn));
    });
  }

  // ---------- Pre-warm status ----------
  async function loadPrewarmStatus() {
    try {
      const res = await fetch("/api/admin/prewarm/status", { credentials: "include" });
      if (!res.ok) throw new Error("Could not load pre-warm status.");
      const status = await res.json();
      const pct = status.total ? Math.round((status.generated / status.total) * 100) : 0;
      el("prewarm-status").innerHTML = `
        <span class="prewarm-count">${status.generated} / ${status.total} renders</span>
        <div class="prewarm-bar-track"><div class="prewarm-bar-fill" style="width:${pct}%;"></div></div>
        <span>${status.enabled ? `Running, one every ${status.interval_seconds}s` : "Paused (PREWARM_ENABLED=false)"}</span>
        <button class="btn btn-ghost btn-sm" id="prewarm-run-now">Generate one now</button>`;
      el("prewarm-run-now").addEventListener("click", async (e) => {
        e.target.disabled = true;
        e.target.textContent = "Generating…";
        try {
          await fetch("/api/admin/prewarm/run-now?count=1", { method: "POST", credentials: "include" });
          await load();
          await loadPrewarmStatus();
        } catch (err) {
          alert(err.message);
        }
      });
    } catch (err) {
      el("prewarm-status").innerHTML = `<div class="empty-state">${err.message}</div>`;
    }
  }

  load();
  loadPrewarmStatus();

  // ---------- Region availability ----------
  async function loadRegions() {
    try {
      const res = await fetch("/api/admin/regions", { credentials: "include" });
      if (!res.ok) throw new Error("Could not load regions.");
      const regions = await res.json();
      renderRegionGroup("region-grid-us", regions.filter((r) => r.country === "US"));
      renderRegionGroup("region-grid-ca", regions.filter((r) => r.country === "CA"));
    } catch (err) {
      el("region-grid-us").innerHTML = `<div class="empty-state">${err.message}</div>`;
    }
  }

  function renderRegionGroup(gridId, regionList) {
    const grid = el(gridId);
    grid.innerHTML = "";
    regionList.forEach((r) => {
      const isLocked = r.country === "US" && r.code === "CA";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `region-toggle${r.is_enabled ? " is-enabled" : ""}${isLocked ? " is-locked" : ""}`;
      btn.innerHTML = `
        <span class="region-code">${r.code}</span>
        <span class="region-name">${r.name}</span>
        <span class="region-state">${isLocked ? "LEGAL" : r.is_enabled ? "ON" : "OFF"}</span>`;
      if (isLocked) {
        btn.title = "Blocked separately due to franchise law — not togglable here.";
      } else {
        btn.addEventListener("click", () => toggleRegion(r.country, r.code, btn));
      }
      grid.appendChild(btn);
    });
  }

  async function toggleRegion(country, code, btn) {
    btn.disabled = true;
    try {
      const res = await fetch(`/api/admin/regions/${country}/${code}/toggle`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error("Toggle failed.");
      const updated = await res.json();
      btn.classList.toggle("is-enabled", updated.is_enabled);
      btn.querySelector(".region-state").textContent = updated.is_enabled ? "ON" : "OFF";
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
    }
  }

  document.querySelectorAll(".region-bulk-actions button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const country = btn.dataset.country;
      const enabled = btn.dataset.enabled === "true";
      const label = country === "US" ? "US states" : "Canadian provinces";
      if (!confirm(`${enabled ? "Enable" : "Disable"} all ${label}?`)) return;
      try {
        const res = await fetch(`/api/admin/regions/${country}/bulk?enabled=${enabled}`, {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) throw new Error("Bulk update failed.");
        await loadRegions();
      } catch (err) {
        alert(err.message);
      }
    });
  });

  loadRegions();
})();
