(() => {
  const state = {
    sessionId: null,
    user: null,
    chatState: {},
    images: [], // {label, url}
    activeImageUrl: null,
    vehicleOptions: [],
    selectedOption: null,
    selecting: false,
    checkoutStarted: false,
    checkout: { delivery: null, financing: null, crosssell: null },
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
    wireBuildTray();
    wireCheckoutCta();
    wireCookieNotice();
  }

  function wireCookieNotice() {
    const notice = el("cookie-notice");
    if (!notice) return;
    try {
      if (!localStorage.getItem("df_cookie_ack")) {
        notice.hidden = false;
      }
    } catch (_) {
      // localStorage unavailable (e.g. private browsing) — just don't show it
    }
    const dismissBtn = el("cookie-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () => {
        try {
          localStorage.setItem("df_cookie_ack", "1");
        } catch (_) {}
        notice.hidden = true;
      });
    }
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
    el("gate").classList.remove("is-active");
    el("app-shell").classList.add("is-active");
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
      showLoader("Building your selection…");
      try {
        const turn = await api("/api/chat/message", {
          method: "POST",
          body: { session_id: state.sessionId, message },
        });
        hideLoader();
        appendMessage("assistant", turn.response_text);
        state.chatState = turn.state || state.chatState;
        updateSpecChips();
        updateBuildRail();
        if (turn.vehicle_options && turn.vehicle_options.length) {
          resetBuildVisuals(); // clear anything left from an earlier, already-completed build
        }
        handleBuildImages(turn.build_images || []);
        if (turn.vehicle_options && turn.vehicle_options.length) {
          renderOptions(turn.vehicle_options);
          setStageVisible(false); // the option photos ARE the build-in-progress view now
        }
        if (turn.unavailable_vehicle) {
          appendNotifyCard(turn.unavailable_vehicle);
        }
        setReady(turn.is_ready_for_finance);
      } catch (err) {
        hideLoader();
        const detail = err && err.message ? err.message : "Mind trying again?";
        appendMessage("assistant", `Hmm, that didn't go through: ${detail}`);
      }
    });
  }

  function appendMessage(role, text, richClass) {
    const thread = el("chat-thread");
    const bubble = document.createElement("div");
    bubble.className = `msg msg-${role}${richClass ? " " + richClass : ""}`;
    bubble.textContent = text;
    thread.appendChild(bubble);
    thread.scrollTop = thread.scrollHeight;
    return bubble;
  }

  function showLoader(message) {
    const thread = el("chat-thread");
    const loader = document.createElement("div");
    loader.className = "car-loader";
    loader.id = "car-loader";
    loader.innerHTML = `<span class="car-loader-dot"></span><span>${message}</span>`;
    thread.appendChild(loader);
    thread.scrollTop = thread.scrollHeight;
  }

  function hideLoader() {
    const loader = el("car-loader");
    if (loader) loader.remove();
  }

  function setReady(isReady) {
    if (isReady && !state.checkoutStarted) {
      el("chat-cta-bar").classList.add("is-visible");
    }
    updateBuildStatus(isReady);
  }

  function updateBuildStatus(isReady) {
    const badge = el("build-status");
    const s = state.chatState || {};
    if (isReady) {
      badge.textContent = "Ready";
      badge.className = "badge badge-preferred";
    } else if (s.body_style_preview_rendered || s.options_generated) {
      badge.textContent = "In progress";
      badge.className = "badge badge-progress";
    } else {
      badge.textContent = "Not started";
      badge.className = "badge badge-standard";
    }
  }

  // ---------- Build panel: progress + renders ----------
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
    el("rail-1").classList.toggle("done", !!s.body_style_preview_rendered);
    el("rail-2").classList.toggle("done", !!s.options_generated);
    el("rail-3").classList.toggle("done", !!s.final_set_generated);
  }

  function setStageVisible(visible) {
    el("build-stage").style.display = visible ? "" : "none";
    el("build-thumbs").style.display = visible ? "" : "none";
  }

  function resetBuildVisuals() {
    state.images = [];
    el("build-thumbs").innerHTML = "";
    const stage = el("build-stage");
    stage.classList.remove("loading");
    stage.innerHTML =
      '<div class="placeholder">Once you pick a make and model,<br/>your build will start rendering here.</div>';
    el("selected-option-card").hidden = true;
  }

  function handleBuildImages(images) {
    if (!images.length) return;
    images.forEach((img) => {
      state.images.push(img);
      addThumb(img);
    });
    setMainImage(images[images.length - 1].url, true);
    flagTrayUpdate();
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

  // ---------- Vehicle options: the actual selectable inventory list ----------
  function renderOptions(options) {
    state.vehicleOptions = options;
    const grid = el("options-grid");
    grid.innerHTML = "";

    options.forEach((opt) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "option-card";
      card.innerHTML = `
        ${opt.image_url ? `<img src="${opt.image_url}" alt="${opt.color} ${opt.trim}" />` : '<div class="option-card-imgless"></div>'}
        <div class="option-card-body">
          <div class="option-card-title">${opt.year} ${opt.make} ${opt.model} ${opt.trim}</div>
          <div class="option-card-meta">${opt.color} · ${opt.condition} · ${opt.mileage.toLocaleString()} mi</div>
          <div class="option-card-price">$${opt.price.toLocaleString()}</div>
        </div>`;
      card.addEventListener("click", () => selectOption(opt));
      grid.appendChild(card);
    });

    flagTrayUpdate();
  }

  async function selectOption(opt) {
    if (state.selecting) return;
    state.selecting = true;
    document.querySelectorAll(".option-card").forEach((c) => {
      c.disabled = true;
      c.style.opacity = "0.5";
      c.style.pointerEvents = "none";
    });
    showLoader("Building your selection…");

    try {
      const turn = await api("/api/chat/select-option", {
        method: "POST",
        body: { session_id: state.sessionId, option_id: opt.option_id },
      });
      hideLoader();

      el("options-grid").innerHTML = "";
      state.vehicleOptions = [];
      state.selectedOption = opt;
      setStageVisible(true);
      showSelectedCard(opt);
      celebrate(el("selected-option-card"));

      appendMessage("assistant", turn.response_text);
      state.chatState = turn.state || state.chatState;
      updateSpecChips();
      updateBuildRail();
      handleBuildImages(turn.build_images || []);
      setReady(turn.is_ready_for_finance);
    } catch (err) {
      hideLoader();
      appendMessage("assistant", `Couldn't lock that in: ${err.message}`);
      // Re-enable the cards so the person can actually retry after a failure
      document.querySelectorAll(".option-card").forEach((c) => {
        c.disabled = false;
        c.style.opacity = "";
        c.style.pointerEvents = "";
      });
    } finally {
      state.selecting = false;
    }
  }

  function showSelectedCard(opt) {
    const card = el("selected-option-card");
    card.hidden = false;
    card.innerHTML = `
      ${opt.image_url ? `<img src="${opt.image_url}" alt="" />` : ""}
      <div>
        <div class="option-selected-badge">&check; Selected</div>
        <div class="option-card-title">${opt.year} ${opt.make} ${opt.model} ${opt.trim}</div>
        <div class="option-card-meta">${opt.color} &middot; $${opt.price.toLocaleString()}</div>
      </div>`;
  }

  function celebrate(targetEl) {
    if (!targetEl) return;
    const rect = targetEl.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const colors = ["#4DA8FF", "#9FE0FF", "#FFFFFF", "#4FD1C5"];
    for (let i = 0; i < 28; i++) {
      const p = document.createElement("div");
      p.className = "confetti-particle";
      const angle = Math.random() * Math.PI * 2;
      const dist = 50 + Math.random() * 100;
      p.style.setProperty("--dx", `${Math.cos(angle) * dist}px`);
      p.style.setProperty("--dy", `${Math.sin(angle) * dist}px`);
      p.style.setProperty("--rot", `${Math.random() * 360 - 180}deg`);
      p.style.left = `${cx}px`;
      p.style.top = `${cy}px`;
      p.style.background = colors[i % colors.length];
      document.body.appendChild(p);
      p.addEventListener("animationend", () => p.remove());
    }
  }

  // ---------- Notify-me-when-available (unavailable vehicle requested) ----------
  function appendNotifyCard(requestedVehicle) {
    const thread = el("chat-thread");
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant msg-rich";
    wrap.innerHTML = `
      <div class="notify-card">
        Want us to let you know if a <strong>${requestedVehicle}</strong> becomes available?
        <div class="notify-card-row">
          <input type="email" placeholder="Your email" class="notify-email-input" />
          <button type="button" class="btn btn-primary notify-submit-btn">Notify me</button>
        </div>
      </div>`;
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;

    wrap.querySelector(".notify-submit-btn").addEventListener("click", async () => {
      const emailInput = wrap.querySelector(".notify-email-input");
      const email = emailInput.value.trim();
      if (!email) {
        emailInput.focus();
        return;
      }
      const card = wrap.querySelector(".notify-card");
      try {
        await api("/api/chat/notify-requests", {
          method: "POST",
          body: { session_id: state.sessionId, email, requested_vehicle: requestedVehicle },
        });
        card.innerHTML = `<div class="notify-card-confirmed">&check; We'll email you the moment a ${requestedVehicle} comes in.</div>`;
      } catch (err) {
        card.innerHTML += `<div class="modal-error">${err.message}</div>`;
      }
    });
  }

  // ---------- Mobile build tray (bottom sheet) ----------
  function wireBuildTray() {
    const tab = el("build-tray-tab");
    const backdrop = el("build-tray-backdrop");
    const panel = el("build-panel");
    const closeBtn = el("build-tray-close");
    if (!tab || !panel) return;

    const open = () => {
      panel.classList.add("is-open");
      backdrop.classList.add("is-open");
      tab.classList.remove("has-update");
    };
    const close = () => {
      panel.classList.remove("is-open");
      backdrop.classList.remove("is-open");
    };

    tab.addEventListener("click", open);
    backdrop.addEventListener("click", close);
    if (closeBtn) closeBtn.addEventListener("click", close);
  }

  function flagTrayUpdate() {
    const panel = el("build-panel");
    const tab = el("build-tray-tab");
    if (!panel || !tab) return;
    if (!panel.classList.contains("is-open")) {
      tab.classList.add("has-update");
    }
  }

  // ---------- Auth modal (nav sign in / sign up — unrelated to checkout) ----------
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

  // ---------- Conversational checkout (inline in chat, no modal) ----------
  function wireCheckoutCta() {
    el("continue-btn").addEventListener("click", () => {
      if (state.checkoutStarted) return;
      state.checkoutStarted = true;
      el("chat-cta-bar").classList.remove("is-visible");
      askDelivery();
    });
  }

  function appendChoiceMessage(text, choices) {
    const thread = el("chat-thread");
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant msg-rich";
    const textNode = document.createElement("div");
    textNode.textContent = text;
    wrap.appendChild(textNode);
    const row = document.createElement("div");
    row.className = "choice-row";
    choices.forEach((c) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "choice-pill";
      btn.textContent = c.label;
      btn.addEventListener("click", () => {
        row.querySelectorAll("button").forEach((b) => (b.disabled = true));
        btn.classList.add("chosen");
        appendMessage("user", c.label);
        c.onPick();
      });
      row.appendChild(btn);
    });
    wrap.appendChild(row);
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  function askDelivery() {
    appendChoiceMessage(
      "How should it get to you? (F&I perks shown are placeholders — final details are still being finalized.)",
      [
        { label: "Home delivery", onPick: () => { state.checkout.delivery = "home"; askFinancing(); } },
        { label: "Pick up at the dealership", onPick: () => { state.checkout.delivery = "pickup"; askFinancing(); } },
      ]
    );
  }

  function askFinancing() {
    appendChoiceMessage("How are you paying for it? A soft check never affects your credit score.", [
      {
        label: "Financing independently / cash",
        onPick: () => { state.checkout.financing = "independent"; askCrossSell(); },
      },
      {
        label: "Explore financing options (soft check)",
        onPick: () => { state.checkout.financing = "dealer_financing"; askCrossSell(); },
      },
    ]);
  }

  function askCrossSell() {
    appendChoiceMessage("If pricing or availability shifts slightly, can the dealer offer a close match?", [
      { label: "Yes, show close matches", onPick: () => { state.checkout.crosssell = true; afterCrossSell(); } },
      { label: "No, this exact vehicle only", onPick: () => { state.checkout.crosssell = false; afterCrossSell(); } },
    ]);
  }

  function afterCrossSell() {
    if (state.user) {
      submitLeadInline();
    } else {
      appendInlineAuthCard();
    }
  }

  function appendInlineAuthCard() {
    const thread = el("chat-thread");
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant msg-rich msg-auth-card";
    wrap.innerHTML = `
      <div class="auth-card-intro">Last step — create an account so I can email you the details and you can come back to this build anytime.</div>
      <div class="modal-tabs">
        <button type="button" class="modal-tab active" data-tab="signup">Sign up</button>
        <button type="button" class="modal-tab" data-tab="signin">Sign in</button>
      </div>
      <form>
        <input type="email" placeholder="Email" required class="inline-auth-email" />
        <input type="password" placeholder="Password" required minlength="8" class="inline-auth-password" />
        <button type="submit" class="btn btn-primary btn-block">Create account</button>
      </form>
      <div class="modal-error" hidden></div>`;
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;

    let mode = "signup";
    const tabs = wrap.querySelectorAll(".modal-tab");
    const submitBtn = wrap.querySelector("button[type=submit]");
    tabs.forEach((t) =>
      t.addEventListener("click", () => {
        tabs.forEach((x) => x.classList.toggle("active", x === t));
        mode = t.dataset.tab;
        submitBtn.textContent = mode === "signup" ? "Create account" : "Sign in";
      })
    );

    wrap.querySelector("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = wrap.querySelector(".inline-auth-email").value.trim();
      const password = wrap.querySelector(".inline-auth-password").value;
      const errorBox = wrap.querySelector(".modal-error");
      errorBox.hidden = true;
      try {
        const path = mode === "signup" ? "/api/auth/signup?role=consumer" : "/api/auth/login";
        state.user = await api(path, { method: "POST", body: { email, password } });
        updateAuthButtons();
        wrap.querySelector("form").remove();
        tabs.forEach((t) => t.remove());
        wrap.querySelector(".auth-card-intro").textContent = "You're in — wrapping up now.";
        await submitLeadInline();
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      }
    });
  }

  async function submitLeadInline() {
    try {
      const lead = await api("/api/leads", {
        method: "POST",
        body: {
          session_id: state.sessionId,
          is_home_delivery: state.checkout.delivery === "home",
          funding_strategy: state.checkout.financing,
          dealer_cross_sell_allowed: !!state.checkout.crosssell,
        },
      });
      appendLeadConfirmation(lead);
    } catch (err) {
      appendMessage("assistant", `Couldn't finish that: ${err.message}`);
    }
  }

  function appendLeadConfirmation(lead) {
    const thread = el("chat-thread");
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant msg-rich";
    wrap.innerHTML = `
      <div>You're all set. Here's what's heading to the dealer:</div>
      <dl class="confirm-summary">
        <dt>Vehicle</dt><dd>${lead.vehicle_specs || "—"}</dd>
        <dt>Dealer</dt><dd>${lead.dealer_name || "—"}</dd>
      </dl>
      <div class="next-steps-note">
        Here's what happens next:
        <ul>
          <li>We'll email you a welcome message with your build's render and the dealership's details</li>
          <li>You'll get delivery or pickup details as soon as they're confirmed</li>
          <li>Sign back in anytime to check on it — your build is saved to your account</li>
        </ul>
      </div>`;
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
