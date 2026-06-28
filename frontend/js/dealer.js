(() => {
  const el = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const res = await fetch(path, {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    if (!res.ok) {
      let detail = "Something went wrong.";
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  }

  async function init() {
    let user = null;
    try {
      user = await api("/api/auth/me");
    } catch (_) {}

    if (user && user.role === "dealer") {
      await showDashboard();
    } else {
      wireGateForm();
    }
  }

  function wireGateForm() {
    document.querySelectorAll(".modal-tab").forEach((tab) => {
      tab.addEventListener("click", () => setTab(tab.dataset.tab));
    });

    el("dealer-auth-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const tab = document.querySelector(".modal-tab.active").dataset.tab;
      const email = el("dealer-email").value.trim();
      const password = el("dealer-password").value;
      const errorBox = el("dealer-error");
      errorBox.hidden = true;

      try {
        if (tab === "signin") {
          await api("/api/auth/login", { method: "POST", body: { email, password } });
        } else {
          const dealer_name = el("dealer-name").value.trim();
          await api("/api/auth/signup?role=dealer", {
            method: "POST",
            body: { email, password, dealer_name },
          });
        }
        await showDashboard();
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      }
    });
  }

  function setTab(tab) {
    document.querySelectorAll(".modal-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    el("dealer-name-field").hidden = tab !== "signup";
    el("dealer-submit").textContent = tab === "signin" ? "Sign in" : "Start free trial";
  }

  async function showDashboard() {
    let data;
    try {
      data = await api("/api/dealer/dashboard");
    } catch (err) {
      el("dealer-error").textContent = err.message;
      el("dealer-error").hidden = false;
      return;
    }

    el("dealer-gate").classList.add("is-hidden");
    el("dealer-dashboard").classList.remove("is-hidden");
    el("nav-signout").hidden = false;
    el("nav-signout").addEventListener("click", async () => {
      await api("/api/auth/logout", { method: "POST" });
      location.reload();
    });

    renderBanner(data);
    el("stat-leads").textContent = data.leads.length;
    el("stat-sync").textContent = data.inventory_sync_status;
    el("stat-account").textContent = data.is_vicimus_client ? "Vicimus client" : "Free trial";

    renderLeads(data.leads);
  }

  function renderBanner(data) {
    const banner = el("status-banner");
    if (data.is_vicimus_client) {
      banner.className = "banner client";
      banner.innerHTML = `<span><strong>${data.dealer_name}</strong> — Vicimus client. Leads and inventory sync are included.</span>`;
    } else {
      const ends = data.trial_ends_at ? new Date(data.trial_ends_at).toLocaleDateString() : "soon";
      banner.className = "banner trial";
      banner.innerHTML = `<span><strong>${data.dealer_name}</strong> — free trial, ends ${ends}.</span><button class="btn btn-primary" disabled>Upgrade (coming soon)</button>`;
    }
  }

  function renderLeads(leads) {
    const container = el("leads-container");
    if (!leads.length) {
      container.innerHTML = `<div class="empty-state">No leads routed here yet.<br/>Once a buyer completes a build that matches your lot, it'll show up here in real time.</div>`;
      return;
    }
    const rows = leads
      .map(
        (l) => `<tr>
          <td>${l.vehicle_specs || "—"}</td>
          <td>${l.status}</td>
          <td>${new Date(l.created_at).toLocaleDateString()}</td>
        </tr>`
      )
      .join("");
    container.innerHTML = `
      <table class="lead-table">
        <thead><tr><th>Vehicle</th><th>Status</th><th>Received</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
