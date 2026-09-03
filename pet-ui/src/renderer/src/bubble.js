const PURIFY = {
  ALLOWED_TAGS: ["p", "br", "strong", "em", "b", "i", "ul", "ol", "li", "code", "pre", "h1", "h2", "h3", "h4", "a", "blockquote", "table", "thead", "tbody", "tr", "th", "td"],
  ALLOWED_ATTR: ["href"],
  ALLOWED_URI_REGEXP: /^https:/i,
  FORBID_TAGS: ["img", "video", "audio", "iframe", "object", "embed", "form", "input", "script", "style"],
};

let streamEl = null;
let streamText = "";
let streamStatus = "";
let currentPanel = "today";

function parseMarkdown(text) {
  const lib = window.marked;
  if (!lib) {
    throw new Error("缺少 marked，无法渲染 Markdown。");
  }
  const parse = typeof lib.parse === "function" ? lib.parse.bind(lib) : lib.marked;
  if (typeof parse !== "function") {
    throw new Error("marked 没有 parse，无法渲染 Markdown。");
  }
  return parse(text, { breaks: true, gfm: true, async: false });
}

function fillBody(el, role, text) {
  if (role === "user") {
    el.textContent = text;
    return;
  }
  if (!window.DOMPurify) {
    throw new Error("缺少 DOMPurify，无法安全渲染 Markdown。");
  }
  const dirty = parseMarkdown(text);
  el.innerHTML = window.DOMPurify.sanitize(dirty, PURIFY);
  el.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      window.open(a.getAttribute("href"), "_blank");
    });
  });
}

function kindLabel(kind) {
  if (kind === "task") {
    return "待办";
  }
  if (kind === "event") {
    return "日程";
  }
  return "今日";
}

export function initBubble() {
  const log = document.getElementById("log");
  const input = document.getElementById("input");
  const closeBtn = document.getElementById("close");
  const clearBtn = document.getElementById("clear");
  const bubble = document.getElementById("bubble");
  const tabs = document.getElementById("tabs");
  const todayBanner = document.getElementById("today-banner");
  const todayFocus = document.getElementById("today-focus");
  const todayRest = document.getElementById("today-rest");
  const todayRefresh = document.getElementById("today-refresh");
  const maaStatus = document.getElementById("maa-status");
  const maaOpts = document.getElementById("maa-opts");
  const maaOpen = document.getElementById("maa-open");
  const maaStart = document.getElementById("maa-start");
  const maaStop = document.getElementById("maa-stop");

  function panelEl(name) {
    return document.getElementById("panel-" + name);
  }

  function setPanel(name) {
    currentPanel = name === "maa" || name === "chat" ? name : "today";
    document.body.dataset.panel = currentPanel;
    ["today", "maa", "chat"].forEach((key) => {
      const el = panelEl(key);
      el.hidden = key !== currentPanel;
    });
    tabs.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.panel === currentPanel);
    });
    if (currentPanel === "today") {
      void loadToday(false);
    }
    if (currentPanel === "maa") {
      void loadMaa();
    }
    if (currentPanel === "chat") {
      input.focus();
    }
  }

  function appendMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const who = document.createElement("div");
    who.className = "who";
    who.textContent = role === "user" ? "你" : "凯尔希";
    const body = document.createElement("div");
    body.className = "body";
    fillBody(body, role, text);
    wrap.appendChild(who);
    wrap.appendChild(body);
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
  }

  function loadHistory(rows) {
    log.innerHTML = "";
    (rows || []).forEach((rec) => {
      const role = rec.role === "user" ? "user" : rec.role === "err" ? "err" : "pet";
      appendMessage(role, rec.text);
    });
  }

  function setBusy(busy) {
    input.disabled = !!busy;
    if (!busy && currentPanel === "chat") {
      input.focus();
    }
  }

  function makePetWrap(role) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const who = document.createElement("div");
    who.className = "who";
    who.textContent = "凯尔希";
    const status = document.createElement("div");
    status.className = "status";
    const body = document.createElement("div");
    body.className = "body";
    wrap.appendChild(who);
    wrap.appendChild(status);
    wrap.appendChild(body);
    return wrap;
  }

  function beginStream() {
    if (streamEl) {
      endStream(streamText, "pet");
    }
    setPanel("chat");
    streamText = "";
    streamStatus = "";
    streamEl = makePetWrap("pet");
    streamEl.classList.add("streaming");
    streamEl.querySelector(".body").textContent = "…";
    log.appendChild(streamEl);
    log.scrollTop = log.scrollHeight;
  }

  function appendStream(piece) {
    if (!piece) {
      return;
    }
    if (!streamEl) {
      beginStream();
    }
    streamText += piece;
    streamEl.querySelector(".body").textContent = streamText;
    log.scrollTop = log.scrollHeight;
  }

  function setStreamStatus(text) {
    if (!streamEl) {
      beginStream();
    }
    streamStatus = text || "";
    streamEl.querySelector(".status").textContent = streamStatus;
    if (!streamText) {
      streamEl.querySelector(".body").textContent = "";
    }
    log.scrollTop = log.scrollHeight;
  }

  function endStream(finalText, role) {
    const text = finalText == null || finalText === "" ? streamText : finalText;
    const kind = role === "err" ? "err" : "pet";
    if (!streamEl) {
      if (text) {
        appendMessage(kind, text);
      }
      return;
    }
    streamEl.className = "msg " + kind;
    streamEl.classList.remove("streaming");
    const status = streamEl.querySelector(".status");
    if (status) {
      status.remove();
    }
    fillBody(streamEl.querySelector(".body"), kind, text || "");
    streamEl = null;
    streamText = "";
    streamStatus = "";
    log.scrollTop = log.scrollHeight;
  }

  function renderToday(data) {
    const err = (data && data.error) || "";
    if (err) {
      todayBanner.hidden = false;
      todayBanner.textContent = err;
    } else {
      todayBanner.hidden = true;
      todayBanner.textContent = "";
    }
    const focus = (data && data.focus) || { kind: "empty", title: "还没有今日数据。", when: "" };
    todayFocus.innerHTML = "";
    const kicker = document.createElement("div");
    kicker.className = "kicker";
    kicker.textContent = focus.kind === "empty" ? "重点" : "重点 · " + kindLabel(focus.kind);
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = focus.title || "今天没有必须盯的事";
    todayFocus.appendChild(kicker);
    todayFocus.appendChild(title);
    if (focus.when) {
      const when = document.createElement("div");
      when.className = "when";
      when.textContent = focus.when;
      todayFocus.appendChild(when);
    }
    todayRest.innerHTML = "";
    (data.rest || []).forEach((item) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = item.title;
      const when = document.createElement("span");
      when.className = "when";
      when.textContent = item.when || kindLabel(item.kind);
      li.appendChild(name);
      li.appendChild(when);
      todayRest.appendChild(li);
    });
    if (data.more > 0) {
      const li = document.createElement("li");
      li.textContent = "还有 " + data.more + " 件，打开看板看全";
      todayRest.appendChild(li);
    }
  }

  function loadToday(refresh) {
    return window.petAPI.call("bubble_today", { refresh: Boolean(refresh) }).then((data) => {
      renderToday(data);
    }).catch((err) => {
      renderToday({
        error: String(err && err.message ? err.message : err),
        focus: { kind: "empty", title: "今日安排读不到。", when: "" },
        rest: [],
        more: 0,
      });
    });
  }

  function renderMaa(snap) {
    maaStatus.textContent = (snap && snap.message) || (snap && snap.status) || "还没开始。";
    maaOpts.innerHTML = "";
    (snap && snap.options ? snap.options : []).forEach((opt) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      const on = Boolean(opt.checked);
      // 透明窗里原生 checkbox 点不到；用按钮，点击路径和「开始」相同。
      btn.type = "button";
      btn.className = "check";
      btn.setAttribute("aria-checked", on ? "true" : "false");
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.setAttribute("aria-hidden", "true");
      btn.appendChild(mark);
      btn.appendChild(document.createTextNode(opt.label));
      btn.addEventListener("click", () => {
        const nextChecked = btn.getAttribute("aria-checked") !== "true";
        window.petAPI.call("maa_set_option", { id: opt.id, checked: nextChecked }).then((next) => {
          renderMaa(next);
        }).catch((err) => {
          maaStatus.textContent = String(err && err.message ? err.message : err);
        });
      });
      li.appendChild(btn);
      maaOpts.appendChild(li);
    });
  }

  function loadMaa() {
    return window.petAPI.call("maa_menu", {}).then((snap) => {
      renderMaa(snap);
    }).catch((err) => {
      maaStatus.textContent = String(err && err.message ? err.message : err);
      maaOpts.innerHTML = "";
    });
  }

  function runMaa(method) {
    return window.petAPI.call(method, {}).then((result) => {
      if (result && result.message) {
        maaStatus.textContent = result.message;
      }
      return loadMaa();
    }).catch((err) => {
      maaStatus.textContent = String(err && err.message ? err.message : err);
    });
  }

  input.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") {
      return;
    }
    const text = input.value.trim();
    if (!text || input.disabled) {
      return;
    }
    input.value = "";
    setPanel("chat");
    window.petAPI.call("send_chat", { text });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      hideBubble();
    }
  });
  closeBtn.addEventListener("click", () => hideBubble());
  clearBtn.addEventListener("click", () => window.petAPI.call("clear_chat", {}));
  bubble.addEventListener("pointerdown", () => {
    window.dispatchEvent(new Event("pet-need-mouse"));
  });
  tabs.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-panel]");
    if (!btn) {
      return;
    }
    setPanel(btn.dataset.panel);
  });
  todayRefresh.addEventListener("click", () => {
    void loadToday(true);
  });
  maaOpen.addEventListener("click", () => {
    void runMaa("maa_open_game");
  });
  maaStart.addEventListener("click", () => {
    void runMaa("maa_start_daily");
  });
  maaStop.addEventListener("click", () => {
    void runMaa("maa_stop");
  });

  function showBubble(panel) {
    return window.petAPI.setBubble(true).then(() => {
      bubble.hidden = false;
      setPanel(panel || currentPanel || "today");
    });
  }

  function hideBubble() {
    bubble.hidden = true;
    return window.petAPI.setBubble(false);
  }

  function isOpen() {
    return !bubble.hidden;
  }

  function hitBubble(x, y) {
    if (bubble.hidden) {
      return false;
    }
    const rect = bubble.getBoundingClientRect();
    return x >= rect.left && x < rect.right && y >= rect.top && y < rect.bottom;
  }

  return {
    appendMessage,
    loadHistory,
    setBusy,
    beginStream,
    appendStream,
    setStreamStatus,
    endStream,
    showBubble,
    hideBubble,
    isOpen,
    hitBubble,
    setPanel,
    showChat() {
      return showBubble("chat");
    },
    showNotice() {
      return showBubble("chat");
    },
    showPanel(panel) {
      return showBubble(panel);
    },
    todayNotice(text) {
      todayBanner.hidden = false;
      todayBanner.textContent = text || "";
      return showBubble("today");
    },
    maaNotice(text) {
      maaStatus.textContent = text || "";
      return showBubble("maa").then(() => loadMaa());
    },
  };
}
