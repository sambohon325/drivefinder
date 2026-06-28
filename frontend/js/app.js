(() => {
  const state = {
    sessionId: null,
    user: null,
    chatState: {},
    images: [], // {label, url}
    activeImageUrl: null,
    pendingAuthIntent: null, // "checkout" once auth succeeds mid-checkout
    checkout: { delivery: "home", financing: "independent", crosssell: "yes" },
  };

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
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  // ---------- Boot ----------
  async function init() {
    try {
      state.user = await api("/api/auth/me");
    } catch (_) {
      state.user = null;
    }
    updateAuthButtons();
    wireGate();
    wireChat();
    wireAuthModal();
    wireCheckoutModal();
  }

  function updateAuthButtons() {
    if (state.user) {
      el("nav-signin").textContent = state.user.email;
      el("nav-signup").textContent = "Sign out";
    }
  }

  // ---------- Gate ----------
  function wireGate() {
    el("gate-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const location = el("gate-location").value.trim();
      const submitBtn = e.target.querySelector("button");
      submitBtn.disabled = true;
      try {
        const turn = await api("/api/chat/start", { method: "POST", body: { location } });
        if (turn.geo_blocked) {
          el("gate-form").style.display = "none";
          const blocked = el("gate-blocked");
          blocked.style.display = "block";
          blocked.textContent = turn.response_text;
          return;
        }
        await openChat(turn);
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  async function openChat(turn) {
    state.sessionId = turn.session_id;
    el("gate").hidden = true;
    el("app-shell").hidden = false;
    appendMessage("assistant", turn.response_text);
  }

  // ---------- Chat ----------
  function wireChat() {
    el("chat-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = el("chat-input");
      const message = input.value.trim();
      if (!message) return;
      input.value = "";
      appendMessage("user", message);
      showTyping();
      try {
        const turn = await api("/api/chat/message", {
          method: "POST",
          body: { session_id: state.sessionId, message },
        });
        hideTyping();
        appendMessage("assistant", turn.response_text);
        state.chatState = turn.state || state.chatState;
        updateSpecChips();
        updateBuildRail();
        handleBuildImages(turn.build_images || []);
        el("continue-btn").disabled = !turn.is_ready_for_finance;
        if (turn.is_ready_for_finance) {
          el("build-status").textContent = "Ready";
          el("build-status").className = "badge badge-preferred";
        }
      } catch (err) {
        hideTyping();
        appendMessage("assistant", "Hmm, that didn't go through. Mind trying again?");
      }
    });
  }

  function appendMessage(role, text) {
    const thread = el("chat-thread");
    const bubble = document.createElement("div");
    bubble.className = `msg msg-${role}`;
    bubble.textContent = text;
    thread.appendChild(bubble);
    thread.scrollTop = thread.scrollHeight;
  }

  function showTyping() {
    const thread = el("chat-thread");
    const dots = document.createElement("div");
    dots.className = "typing-dots";
    dots.id = "typing-indicator";
    dots.innerHTML = "<span></span><span></span><span></span>";
    thread.appendChild(dots);
    thread.scrollTop = thread.scrollHeight;
  }

  function hideTyping() {
    const dots = el("typing-indicator");
    if (dots) dots.remove();
  }

  // ---------- Build panel ----------
  function updateSpecChips() {
    const s = state.chatState || {};
    setChip("chip-make", "Make", s.current_make);
    setChip("chip-model", "Model", s.current_model);
    setChip("chip-color", "Color", s.stock_color);
    setChip("chip-body", "Body", s.current_body_style);
  }

  function setChip(id, label, value) {
    const chip = el(id);
    const has = value && value !== "none";
    chip.textContent = `${label} ${has ? "— " + value : "—"}`;
    chip.classList.toggle("set", !!has);
  }

  function updateBuildRail() {
    const s = state.chatState || {};
    el("rail-1").classList.toggle("done", !!s.clay_rendered);
    el("rail-2").classList.toggle("done", !!s.previews_generated);
    el("rail-3").classList.toggle("done", !!s.final_set_generated);
  }

  function handleBuildImages(images) {
    if (!images.length) return;
    images.forEach((img) => {
      state.images.push(img);
      addThumb(img);
    });
    setMainImage(images[images.length - 1].url, true);
  }

  function addThumb(img) {
    const thumbs = el("build-thumbs");
    const thumb = document.createElement("img");
    thumb.src = img.url;
    thumb.alt = img.label;
    thumb.title = img.label;
    thumb.addEventListener("click", () => setMainImage(img.url, false));
    thumbs.appendChild(thumb);
  }

  function setMainImage(url, animate) {
    state.activeImageUrl = url;
    const stage = el("build-stage");
    stage.classList.remove("loading");
    stage.innerHTML = "";
    const image = document.createElement("img");
    image.src = url;
    stage.appendChild(image);
    if (animate) {
      const scan = document.createElement("div");
      scan.className = "scan-line";
      stage.appendChild(scan);
      scan.addEventListener("animationend", () => scan.remove());
    }
    document.querySelectorAll(".build-thumbs img").forEach((t) => {
      t.classList.toggle("active", t.src.endsWith(url));
    });
  }

  // ---------- Auth modal ----------
  function wireAuthModal() {
    el("nav-signin").addEventListener("click", () => {
      if (state.user) return logout();
      openAuthModal("signin");
    });
    el("nav-signup").addEventListener("click", () => {
      if (state.user) return logout();
      openAuthModal("signup");
    });
    el("auth-close").addEventListener("click", () => closeModal("auth-modal"));

    document.querySelectorAll(".modal-tab").forEach((tab) => {
      tab.addEventListener("click", () => setAuthTab(tab.dataset.tab));
    });

    el("auth-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const tab = document.querySelector(".modal-tab.active").dataset.tab;
      const email = el("auth-email").value.trim();
      const password = el("auth-password").value;
      const errorBox = el("auth-error");
      errorBox.hidden = true;
      try {
        const path = tab === "signin" ? "/api/auth/login" : "/api/auth/signup?role=consumer";
        state.user = await api(path, { method: "POST", body: { email, password } });
        updateAuthButtons();
        closeModal("auth-modal");
        if (state.pendingAuthIntent === "checkout") {
          state.pendingAuthIntent = null;
          await finalizeCheckout();
        }
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      }
    });
  }

  function setAuthTab(tab) {
    document.querySelectorAll(".modal-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    if (tab === "signin") {
      el("auth-title").textContent = "Welcome back";
      el("auth-sub").textContent = "Sign in to pick up where you left off.";
      el("auth-submit").textContent = "Sign in";
    } else {
      el("auth-title").textContent = "Create your account";
      el("auth-sub").textContent = "So you can track this lead and come back to your build anytime.";
      el("auth-submit").textContent = "Sign up";
    }
  }

  function openAuthModal(tab) {
    setAuthTab(tab);
    el("auth-error").hidden = true;
    el("auth-modal").hidden = false;
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    state.user = null;
    el("nav-signin").textContent = "Sign in";
    el("nav-signup").textContent = "Sign up";
  }

  function closeModal(id) {
    el(id).hidden = true;
  }

  // ---------- Checkout modal ----------
  function wireCheckoutModal() {
    el("continue-btn").addEventListener("click", () => {
      goToCheckoutStep("delivery");
      el("checkout-modal").hidden = false;
    });
    el("checkout-close").addEventListener("click", () => closeModal("checkout-modal"));

    el("delivery-next").addEventListener("click", () => {
      state.checkout.delivery = document.querySelector('input[name="delivery"]:checked').value;
      goToCheckoutStep("financing");
    });
    el("financing-next").addEventListener("click", () => {
      state.checkout.financing = document.querySelector('input[name="financing"]:checked').value;
      goToCheckoutStep("crosssell");
    });
    el("crosssell-next").addEventListener("click", async () => {
      state.checkout.crosssell = document.querySelector('input[name="crosssell"]:checked').value;
      if (!state.user) {
        state.pendingAuthIntent = "checkout";
        closeModal("checkout-modal");
        openAuthModal("signup");
        return;
      }
      await finalizeCheckout();
    });
    el("confirm-done").addEventListener("click", () => closeModal("checkout-modal"));
  }

  function goToCheckoutStep(step) {
    document.querySelectorAll(".checkout-step").forEach((s) => {
      s.classList.toggle("active", s.dataset.step === step);
    });
  }

  async function finalizeCheckout() {
    try {
      const lead = await api("/api/leads", {
        method: "POST",
        body: {
          session_id: state.sessionId,
          is_home_delivery: state.checkout.delivery === "home",
          funding_strategy: state.checkout.financing,
          dealer_cross_sell_allowed: state.checkout.crosssell === "yes",
        },
      });
      renderConfirmSummary(lead);
      el("checkout-modal").hidden = false;
      goToCheckoutStep("confirm");
    } catch (err) {
      appendMessage("assistant", `Couldn't finish that: ${err.message}`);
    }
  }

  function renderConfirmSummary(lead) {
    const badge = lead.is_preferred_dealer
      ? '<span class="badge badge-preferred">Preferred dealer</span>'
      : '<span class="badge badge-standard">Standard dealer</span>';
    el("confirm-summary").innerHTML = `
      <dt>Vehicle</dt><dd>${lead.vehicle_specs || "—"}</dd>
      <dt>Dealer</dt><dd>${lead.dealer_name || "—"} ${badge}</dd>
      <dt>Status</dt><dd>${lead.status}</dd>
    `;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
