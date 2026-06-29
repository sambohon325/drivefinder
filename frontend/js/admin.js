(() => {
  const el = (id) => document.getElementById(id);
  let allImages = [];

  // ---------- Cached renders ----------
  async function load() {
    const grid = el("admin-grid");
    grid.innerHTML = '<div class="empty-state">Loading…</div>';
    try {
      const res = await fetch("/api/admin/images", { credentials: "include" });
      if (!res.ok) throw new Error("Could not load cached renders.");
      allImages = await res.json();
      render(allImages);
    } catch (err) {
      grid.innerHTML = `<div class="empty-state">${err.message}</div>`;
    }
  }

  function render(images) {
    const grid = el("admin-grid");
    if (!images.length) {
      grid.innerHTML = '<div class="empty-state">No cached renders yet.</div>';
      return;
    }
    grid.innerHTML = "";
    images.forEach((img) => {
      const card = document.createElement("div");
      card.className = "admin-card";
      card.innerHTML = `
        <img src="${img.url}" alt="${img.filename}" loading="lazy" />
        <div class="admin-card-body">
          <div class="admin-card-name">${img.filename}</div>
          <div class="admin-card-meta">${img.size_kb} KB &middot; ${new Date(img.modified * 1000).toLocaleString()}</div>
          <button class="btn btn-ghost admin-delete-btn" data-filename="${img.filename}">Delete</button>
        </div>`;
      grid.appendChild(card);
    });

    grid.querySelectorAll(".admin-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const filename = btn.dataset.filename;
        if (!confirm(`Delete ${filename}? It'll regenerate next time it's needed.`)) return;
        btn.disabled = true;
        btn.textContent = "Deleting…";
        try {
          const res = await fetch(`/api/admin/images/${filename}`, {
            method: "DELETE",
            credentials: "include",
          });
          if (!res.ok) throw new Error("Delete failed.");
          await load();
        } catch (err) {
          btn.disabled = false;
          btn.textContent = "Delete";
          alert(err.message);
        }
      });
    });
  }

  el("filter-input").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    render(allImages.filter((i) => i.filename.toLowerCase().includes(q)));
  });

  load();

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

