(() => {
  const API = "/api/pulse";
  const $ = (selector) => document.querySelector(selector);
  const feedEl = $("#pulseFeed");
  const authorEl = $("#pulseAuthor");
  const handleEl = $("#pulseHandle");
  const bodyEl = $("#pulseBody");
  const countEl = $("#pulseCount");
  const publishEl = $("#pulsePublish");
  const stateEl = $("#pulseState");
  const moreEl = $("#pulseMore");
  let nextBefore = null;
  let replyTo = null;

  const actor = localStorage.getItem("quanticPulseActor") || (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));
  const profile = {
    actor,
    author: localStorage.getItem("quanticPulseAuthor") || "Membre Quantic",
    handle: localStorage.getItem("quanticPulseHandle") || "quantic"
  };
  localStorage.setItem("quanticPulseActor", profile.actor);
  authorEl.value = profile.author;
  handleEl.value = profile.handle;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  }

  function relativeTime(value) {
    const delta = Math.max(0, Date.now() - new Date(value).getTime());
    const minutes = Math.floor(delta / 60000);
    if (minutes < 1) return "à l’instant";
    if (minutes < 60) return String(minutes) + " min";
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return String(hours) + " h";
    return String(Math.floor(hours / 24)) + " j";
  }

  function postMarkup(post) {
    const reply = post.replyTo ? '<span class="pulse-post-reply">Réponse à #' + Number(post.replyTo) + "</span>" : "";
    return '<article class="pulse-post" data-post-id="' + Number(post.id) + '">' +
      '<div class="pulse-post-head">' +
      '<div class="pulse-avatar" aria-hidden="true">' + escapeHtml((post.author || "Q").slice(0, 1).toUpperCase()) + "</div>" +
      '<div class="pulse-post-meta"><strong>' + escapeHtml(post.author) + "</strong><span>@" + escapeHtml(post.handle) + "</span></div>" +
      '<time datetime="' + escapeHtml(post.createdAt) + '">' + relativeTime(post.createdAt) + "</time>" +
      "</div>" +
      '<div class="pulse-post-body">' + reply + escapeHtml(post.body) + "</div>" +
      '<div class="pulse-actions">' +
      '<button type="button" data-action="reply">↩ Répondre <span>' + Number(post.replies || 0) + "</span></button>" +
      '<button type="button" data-action="like">♡ J’aime <span>' + Number(post.likes || 0) + "</span></button>" +
      "</div></article>";
  }

  function setState(kind, text) {
    stateEl.className = "pulse-state " + (kind || "");
    stateEl.querySelector("span").textContent = text;
  }

  function showError(message) {
    const node = document.createElement("div");
    node.className = "pulse-error";
    node.textContent = message;
    feedEl.prepend(node);
    setTimeout(() => node.remove(), 5000);
  }

  async function checkHealth() {
    try {
      const response = await fetch(API + "/health", { cache: "no-store" });
      if (!response.ok) throw new Error();
      setState("online", "Pulse connecté · MySQL");
    } catch {
      setState("offline", "Pulse indisponible");
    }
  }

  async function loadFeed(options = {}) {
    const append = options.append === true;
    if (!append) feedEl.innerHTML = '<div class="pulse-loading">Chargement du fil…</div>';
    const url = new URL(API + "/feed", location.origin);
    url.searchParams.set("limit", "30");
    if (append && nextBefore) url.searchParams.set("before", String(nextBefore));
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || "Fil indisponible.");
      const posts = Array.isArray(payload.posts) ? payload.posts : [];
      if (!append) feedEl.innerHTML = "";
      if (!posts.length && !append) feedEl.innerHTML = '<div class="pulse-empty">Le fil est vide. Publie le premier Pulse.</div>';
      else feedEl.insertAdjacentHTML("beforeend", posts.map(postMarkup).join(""));
      nextBefore = payload.nextBefore || null;
      moreEl.hidden = !nextBefore;
      setState("online", "Pulse connecté · MySQL");
    } catch (error) {
      if (!append) feedEl.innerHTML = '<div class="pulse-error">Impossible de charger le fil Pulse.</div>';
      setState("offline", "Pulse indisponible");
    }
  }

  function saveProfile() {
    profile.author = (authorEl.value || "Membre Quantic").trim().slice(0, 80);
    profile.handle = (handleEl.value || "quantic").trim().replace(/^@+/, "").slice(0, 32);
    localStorage.setItem("quanticPulseAuthor", profile.author);
    localStorage.setItem("quanticPulseHandle", profile.handle);
  }

  function setReply(id) {
    replyTo = id;
    $("#pulseReplyId").textContent = "#" + id;
    $("#pulseReplyBanner").hidden = false;
    bodyEl.focus();
  }

  function clearReply() {
    replyTo = null;
    $("#pulseReplyBanner").hidden = true;
  }

  bodyEl.addEventListener("input", () => { countEl.textContent = String(bodyEl.value.length) + " / 500"; });
  authorEl.addEventListener("change", saveProfile);
  handleEl.addEventListener("change", saveProfile);
  $("#pulseReplyCancel").addEventListener("click", clearReply);
  $("#pulseRefresh").addEventListener("click", () => loadFeed());
  moreEl.addEventListener("click", () => loadFeed({ append: true }));

  $("#pulseCompose").addEventListener("submit", async (event) => {
    event.preventDefault();
    saveProfile();
    const body = bodyEl.value.trim();
    if (!body) return;
    publishEl.disabled = true;
    publishEl.textContent = "Publication…";
    try {
      const response = await fetch(API + "/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ author: profile.author, handle: profile.handle, body, replyTo })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || "Publication impossible.");
      bodyEl.value = "";
      countEl.textContent = "0 / 500";
      clearReply();
      await loadFeed();
    } catch (error) {
      showError(error.message || "Publication impossible.");
    } finally {
      publishEl.disabled = false;
      publishEl.textContent = "Publier";
    }
  });

  feedEl.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    const post = event.target.closest("[data-post-id]");
    if (!button || !post) return;
    const id = Number(post.dataset.postId);
    if (button.dataset.action === "reply") {
      setReply(id);
      return;
    }
    if (button.dataset.action === "like") {
      button.disabled = true;
      try {
        const response = await fetch(API + "/posts/" + id + "/like", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ actor: profile.actor })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload?.error || "Réaction impossible.");
        button.classList.toggle("liked", payload.liked === true);
        button.querySelector("span").textContent = String(payload.likes || 0);
      } catch (error) {
        showError(error.message || "Réaction impossible.");
      } finally {
        button.disabled = false;
      }
    }
  });

  void checkHealth();
  void loadFeed();
})();