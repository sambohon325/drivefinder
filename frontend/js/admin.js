(() => {
  const el = (id) => document.getElementById(id);
  let allImages = [];

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
})();
