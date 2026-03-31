const fallbackTokens = {
  colors: {
    bg: "#090b0f",
    bg_elevated: "#11161c",
    panel: "#151b22",
    panel_alt: "#1a232c",
    border: "#283241",
    text: "#f2f5f7",
    text_muted: "#9eacba",
    accent_ok: "#4fd68b",
    accent_warn: "#e0a84e",
    accent_danger: "#c94747",
    accent_signal: "#6fdbb8"
  },
  typography: {
    display: { family: "Bahnschrift SemiBold", size: 34 },
    title: { family: "Segoe UI Semibold", size: 18 },
    body: { family: "Segoe UI", size: 14 },
    mono: { family: "Consolas", size: 12 }
  },
  layout: {
    shell_padding: 18,
    card_padding: 18,
    compact_threshold: 1320,
    composer_height: 104
  },
  shape: {
    radius: 4,
    border_width: 1
  }
};

const fallbackManifest = {
  name: "JARVIS NEXT",
  modes: ["create", "code", "roblox", "system", "research", "recreate"]
};

const fallbackSceneConfig = {
  name: "first_run_prologue",
  skippable_after_ms: 4000,
  total_duration_ms: 22000,
  scenes: [
    {
      id: "cold_boot",
      duration_ms: 2200,
      text: ["BOOTING CONTROL HUB", "LINKING CORE", "LOADING USER CHANNEL"]
    },
    {
      id: "core_wakeup",
      duration_ms: 3400,
      voice: [
        "Связь установлена.",
        "Я поднимаю ядро доступа и собираю ваш рабочий контур."
      ]
    },
    {
      id: "identity",
      duration_ms: 4200,
      voice: [
        "Я не отдельный бот под одну задачу.",
        "Я — единое ядро: создавать, воссоздавать, писать код, работать с Roblox, выполнять системные действия и держать проектный контекст."
      ]
    },
    {
      id: "modes",
      duration_ms: 3600,
      voice: [
        "Режимы не конкурируют между собой.",
        "Я поднимаю только тот контур, который нужен вам сейчас."
      ]
    },
    {
      id: "access_gate",
      duration_ms: 4200,
      voice: [
        "Сначала откроем доступ.",
        "После этого вы сразу войдёте в главный хаб без лишних мастеров и всплывающих окон."
      ]
    },
    {
      id: "enter_hub",
      duration_ms: 4400,
      voice: [
        "Хаб готов.",
        "Сформулируйте задачу как цель. Остальное я возьму на себя."
      ]
    }
  ]
};

const sceneMeta = {
  cold_boot: {
    eyebrow: "BOOT SEQUENCE",
    title: "Холодный запуск",
    lead: "Я поднимаю ядро, проверяю канал пользователя и готовлю операторский хаб к работе.",
    status: "Холодный запуск",
    footer: "Пролог можно будет пропустить через несколько секунд, но запуск лучше досмотреть целиком."
  },
  core_wakeup: {
    eyebrow: "CORE ONLINE",
    title: "Ядро выходит на связь",
    lead: "Сигнальные панели оживают, контур доступа связывается с пользователем и включает центральную камеру.",
    status: "Ядро на линии",
    footer: "Старые мастера и всплывающие окна больше не нужны. Вход идёт по одной оси."
  },
  identity: {
    eyebrow: "IDENTITY",
    title: "Единый JARVIS",
    lead: "Это не набор разрозненных экранов. Это один мозг, который умеет создавать, кодить, искать и исполнять.",
    status: "Контур личности собран",
    footer: "Проводник хаба появляется только там, где усиливает сцену, а не ломает рабочую поверхность."
  },
  modes: {
    eyebrow: "ACTIVE MODES",
    title: "Контуры без визуальной свалки",
    lead: "Режимы поднимаются по задаче. Пользователь видит одну цель, а не мешанину из дублей и боковых мастеров.",
    status: "Режимы синхронизированы",
    footer: "Wide-режим отдаёт максимум площади диалогу. Compact-режим включает меню только когда это действительно нужно."
  },
  access_gate: {
    eyebrow: "ACCESS GATE",
    title: "Один вход в главный хаб",
    lead: "Регистрация, базовая настройка и рабочая поверхность живут по одной траектории. Без скачков между окнами.",
    status: "Доступ готовится",
    footer: "Если действие рискованное, JARVIS обязан сначала показать dry-run."
  },
  enter_hub: {
    eyebrow: "ENTER HUB",
    title: "Хаб готов",
    lead: "Катсцена должна заканчиваться не пустотой, а живой рабочей поверхностью: чат, голос, контекст и composer.",
    status: "Хаб открыт",
    footer: "После пролога можно сразу продолжать сценарий и держать весь проект в одном контуре."
  }
};

const dom = {};

const runtime = {
  inHub: false,
  skipReady: false,
  sceneConfig: fallbackSceneConfig,
  timers: [],
  clock: null,
  progressStart: 0
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheDom();

  const [tokens, manifest, sceneConfig] = await Promise.all([
    readJson("../design_tokens.json", fallbackTokens),
    readJson("../product_manifest.json", fallbackManifest),
    readJson("../prologue_scene.json", fallbackSceneConfig)
  ]);

  runtime.sceneConfig = sceneConfig;
  applyTokens(tokens);
  applyManifest(manifest);
  bindEvents();
  startMeters();

  const params = new URLSearchParams(window.location.search);
  const forcedState = params.get("state");
  const forcedScene = params.get("scene");

  if (forcedState === "hub") {
    showHubImmediate();
    return;
  }

  if (forcedScene) {
    showScenePreview(sceneConfig, forcedScene);
    return;
  }

  beginPrologue(sceneConfig);
}

function cacheDom() {
  dom.app = document.getElementById("app");
  dom.prologueShell = document.getElementById("prologue-shell");
  dom.hubShell = document.getElementById("hub-shell");
  dom.statusLabel = document.getElementById("status-label");
  dom.sceneCounter = document.getElementById("scene-counter");
  dom.skipButton = document.getElementById("skip-button");
  dom.sceneEyebrow = document.getElementById("scene-eyebrow");
  dom.sceneTitle = document.getElementById("scene-title");
  dom.sceneLead = document.getElementById("scene-lead");
  dom.sceneId = document.getElementById("scene-id");
  dom.sceneLog = document.getElementById("scene-log");
  dom.voiceState = document.getElementById("voice-state");
  dom.voiceLine = document.getElementById("voice-line");
  dom.voiceEcho = document.getElementById("voice-echo");
  dom.voiceMeterFill = document.getElementById("voice-meter-fill");
  dom.hubVoiceMeterFill = document.getElementById("hub-voice-meter-fill");
  dom.progressFill = document.getElementById("progress-fill");
  dom.timeLeft = document.getElementById("time-left");
  dom.footerHint = document.getElementById("footer-hint");
  dom.chatFeed = document.getElementById("chat-feed");
  dom.composerForm = document.getElementById("composer-form");
  dom.composerInput = document.getElementById("composer-input");
  dom.dryRunDemo = document.getElementById("dry-run-demo");
}

async function readJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.warn(`Не удалось загрузить ${path}:`, error);
    return fallback;
  }
}

function applyTokens(tokens) {
  const root = document.documentElement;
  const colors = tokens.colors || {};
  const typography = tokens.typography || {};
  const layout = tokens.layout || {};
  const shape = tokens.shape || {};

  root.style.setProperty("--bg", colors.bg || fallbackTokens.colors.bg);
  root.style.setProperty("--bg-elevated", colors.bg_elevated || fallbackTokens.colors.bg_elevated);
  root.style.setProperty("--panel", colors.panel || fallbackTokens.colors.panel);
  root.style.setProperty("--panel-alt", colors.panel_alt || fallbackTokens.colors.panel_alt);
  root.style.setProperty("--border", colors.border || fallbackTokens.colors.border);
  root.style.setProperty("--text", colors.text || fallbackTokens.colors.text);
  root.style.setProperty("--text-muted", colors.text_muted || fallbackTokens.colors.text_muted);
  root.style.setProperty("--accent-ok", colors.accent_ok || fallbackTokens.colors.accent_ok);
  root.style.setProperty("--accent-warn", colors.accent_warn || fallbackTokens.colors.accent_warn);
  root.style.setProperty("--accent-danger", colors.accent_danger || fallbackTokens.colors.accent_danger);
  root.style.setProperty("--accent-signal", colors.accent_signal || fallbackTokens.colors.accent_signal);
  root.style.setProperty("--display-font", asFontFamily(typography.display?.family || fallbackTokens.typography.display.family));
  root.style.setProperty("--title-font", asFontFamily(typography.title?.family || fallbackTokens.typography.title.family));
  root.style.setProperty("--body-font", asFontFamily(typography.body?.family || fallbackTokens.typography.body.family));
  root.style.setProperty("--mono-font", asFontFamily(typography.mono?.family || fallbackTokens.typography.mono.family));
  root.style.setProperty("--shell-padding", `${layout.shell_padding || fallbackTokens.layout.shell_padding}px`);
  root.style.setProperty("--card-padding", `${layout.card_padding || fallbackTokens.layout.card_padding}px`);
  root.style.setProperty("--compact-threshold", `${layout.compact_threshold || fallbackTokens.layout.compact_threshold}px`);
  root.style.setProperty("--composer-height", `${layout.composer_height || fallbackTokens.layout.composer_height}px`);
  root.style.setProperty("--radius", `${shape.radius || fallbackTokens.shape.radius}px`);
  root.style.setProperty("--border-width", `${shape.border_width || fallbackTokens.shape.border_width}px`);
}

function asFontFamily(value) {
  return value.includes(",") ? value : `"${value}"`;
}

function applyManifest(manifest) {
  document.title = `${manifest.name || "JARVIS NEXT"} // Prototype`;
}

function bindEvents() {
  dom.skipButton.addEventListener("click", enterHub);

  document.addEventListener("keydown", (event) => {
    if (event.key === " " && runtime.skipReady && !runtime.inHub) {
      event.preventDefault();
      enterHub();
    }
  });

  dom.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = dom.composerInput.value.trim();
    if (!value) {
      return;
    }

    appendMessage("Пользователь", value, "user");
    dom.composerInput.value = "";

    window.setTimeout(() => {
      appendMessage("JARVIS", buildReply(value), "assistant");
      dom.chatFeed.scrollTop = dom.chatFeed.scrollHeight;
    }, 380);
  });

  dom.dryRunDemo.addEventListener("click", () => {
    appendMessage(
      "JARVIS",
      "Dry-run: сначала покажу, какие шаги будут выполнены, какие файлы изменятся и где есть риск. Реальное действие начнётся только после подтверждения.",
      "assistant"
    );
    dom.chatFeed.scrollTop = dom.chatFeed.scrollHeight;
  });

  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      dom.composerInput.value = button.dataset.suggestion || "";
      dom.composerInput.focus();
    });
  });
}

function beginPrologue(sceneConfig) {
  const scenes = sceneConfig.scenes || fallbackSceneConfig.scenes;
  const totalDuration = sceneConfig.total_duration_ms || sumDurations(scenes);

  dom.sceneCounter.textContent = `01 / ${String(scenes.length).padStart(2, "0")}`;
  runtime.progressStart = performance.now();

  window.setTimeout(() => {
    runtime.skipReady = true;
    dom.skipButton.hidden = false;
  }, sceneConfig.skippable_after_ms || 4000);

  let offset = 0;
  scenes.forEach((scene, index) => {
    runtime.timers.push(
      window.setTimeout(() => {
        renderScene(scene, index, scenes.length);
      }, offset)
    );
    offset += scene.duration_ms || 0;
  });

  runtime.timers.push(window.setTimeout(enterHub, totalDuration));
  renderScene(scenes[0], 0, scenes.length);
  startClock(totalDuration);
}

function showScenePreview(sceneConfig, sceneId) {
  const scenes = sceneConfig.scenes || fallbackSceneConfig.scenes;
  const index = scenes.findIndex((scene) => scene.id === sceneId);
  const safeIndex = index >= 0 ? index : 0;
  renderScene(scenes[safeIndex], safeIndex, scenes.length);
  dom.skipButton.hidden = false;
  runtime.skipReady = true;
  dom.timeLeft.textContent = "preview";
  dom.progressFill.style.width = `${((safeIndex + 1) / scenes.length) * 100}%`;
}

function renderScene(scene, index, total) {
  const meta = sceneMeta[scene.id] || sceneMeta.cold_boot;
  dom.app.dataset.scene = scene.id;
  dom.sceneCounter.textContent = `${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}`;
  dom.statusLabel.textContent = meta.status;
  dom.sceneEyebrow.textContent = meta.eyebrow;
  dom.sceneTitle.textContent = meta.title;
  dom.sceneLead.textContent = meta.lead;
  dom.sceneId.textContent = scene.id;
  dom.voiceState.textContent = scene.id === "enter_hub" ? "Хаб на линии" : "Слышу контур";
  dom.voiceLine.textContent = scene.voice?.[0] || "Связь установлена.";
  dom.voiceEcho.textContent = scene.voice?.[1] || meta.lead;
  dom.footerHint.textContent = meta.footer;
  renderLog(scene);
}

function renderLog(scene) {
  const lines = scene.text?.length ? scene.text : scene.voice || [];
  dom.sceneLog.innerHTML = "";

  lines.forEach((line, index) => {
    const item = document.createElement("li");
    item.style.setProperty("--delay", `${index * 90}ms`);
    item.textContent = line;
    dom.sceneLog.appendChild(item);
  });
}

function startClock(totalDuration) {
  if (runtime.clock) {
    cancelAnimationFrame(runtime.clock);
  }

  const tick = (now) => {
    if (runtime.inHub) {
      dom.progressFill.style.width = "100%";
      dom.timeLeft.textContent = "0.0с";
      return;
    }

    const elapsed = Math.min(now - runtime.progressStart, totalDuration);
    const progress = totalDuration === 0 ? 1 : elapsed / totalDuration;
    const remaining = Math.max((totalDuration - elapsed) / 1000, 0);

    dom.progressFill.style.width = `${progress * 100}%`;
    dom.timeLeft.textContent = `${remaining.toFixed(1)}с`;
    runtime.clock = requestAnimationFrame(tick);
  };

  runtime.clock = requestAnimationFrame(tick);
}

function startMeters() {
  window.setInterval(() => {
    const prologueLevel = 18 + Math.random() * 62;
    const hubLevel = 22 + Math.random() * 58;
    dom.voiceMeterFill.style.width = `${prologueLevel}%`;
    dom.hubVoiceMeterFill.style.width = `${hubLevel}%`;
  }, 280);
}

function enterHub() {
  if (runtime.inHub) {
    return;
  }

  runtime.inHub = true;
  runtime.skipReady = false;
  dom.skipButton.hidden = true;

  runtime.timers.forEach((timer) => window.clearTimeout(timer));
  runtime.timers = [];

  if (runtime.clock) {
    cancelAnimationFrame(runtime.clock);
  }

  dom.prologueShell.classList.add("is-exiting");
  dom.hubShell.classList.add("is-mounted");

  window.setTimeout(() => {
    dom.prologueShell.hidden = true;
    requestAnimationFrame(() => {
      dom.hubShell.classList.add("is-visible");
    });
  }, 420);
}

function showHubImmediate() {
  runtime.inHub = true;
  dom.prologueShell.hidden = true;
  dom.hubShell.classList.add("is-mounted", "is-visible");
  dom.progressFill.style.width = "100%";
  dom.timeLeft.textContent = "0.0с";
}

function appendMessage(role, text, kind) {
  const article = document.createElement("article");
  article.className = `message message-${kind}`;

  const roleLine = document.createElement("p");
  roleLine.className = "message-role";
  roleLine.textContent = role;

  const body = document.createElement("p");
  body.className = "message-copy";
  body.textContent = text;

  article.append(roleLine, body);
  dom.chatFeed.appendChild(article);
}

function buildReply(value) {
  const normalized = value.toLowerCase();

  if (normalized.includes("roblox")) {
    return "Контур Roblox поднят. Сначала разложу задачу на хаб, игровые петли, готовые ассеты и Luau-каркас, чтобы не генерировать мусор с нуля.";
  }

  if (normalized.includes("ассет") || normalized.includes("дерев")) {
    return "Сначала покажу готовые наборы и только потом предложу генерацию. Для сцены важнее правильный pack и читаемая композиция, чем самодельный шум.";
  }

  if (normalized.includes("dry-run") || normalized.includes("прогон")) {
    return "Сухой прогон включён. Я перечислю шаги, риски и точки изменения до реального исполнения.";
  }

  if (normalized.includes("код") || normalized.includes("luau")) {
    return "Подниму кодовый контур: сначала структура, потом чистая реализация, затем проверка и регрессия.";
  }

  return "Задача принята. Я выберу нужный контур, соберу короткий план исполнения и не буду перегружать главный экран лишними панелями.";
}

function sumDurations(scenes) {
  return scenes.reduce((total, scene) => total + (scene.duration_ms || 0), 0);
}
