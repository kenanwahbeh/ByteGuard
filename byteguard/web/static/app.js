"use strict";

const $ = (id) => document.getElementById(id);
let strings = {};
let language = localStorage.getItem("byteguard-language") || (navigator.language.startsWith("ar") ? "ar" : "en");
let timer = null;

function t(key, values = {}) {
  return (strings[key] || key).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

async function loadLanguage() {
  strings = await (await fetch(`/i18n/${language}.json`)).json();
  document.documentElement.lang = language;
  document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  for (const element of document.querySelectorAll("[data-i18n]")) element.textContent = t(element.dataset.i18n);
  for (const element of document.querySelectorAll("[data-i18n-placeholder]")) {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  }
  $("language").textContent = t("language_switch");
}

class ApiError extends Error {
  constructor(code, message) {
    super(message || code);
    this.code = code;
  }
}

async function api(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { "X-ByteGuard": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("network");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.error || "generic", data.message);
  return data;
}

function notify(text, isError = false) {
  const notice = $("notice");
  notice.textContent = text;
  notice.classList.toggle("error", isError);
  notice.hidden = !text;
}

function explain(error) {
  if (error.code === "login") return showLogin();
  const known = { password: "error_password", locked: "error_locked", network: "error_network" };
  // A refusal from the server carries its own explanation.
  notify(error.code === "refused" ? error.message : t(known[error.code] || "error_generic"), true);
}

function showLogin() {
  clearInterval(timer);
  $("app").hidden = true;
  $("logout").hidden = true;
  $("login").hidden = false;
  $("password").focus();
}

function size(bytes) {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit ? value.toFixed(1) : value} ${units[unit]}`;
}

function when(timestamp) {
  return new Date(timestamp).toLocaleString(language);
}

function button(label, className, action) {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = label;
  if (className) element.className = className;
  element.addEventListener("click", () => action().catch(explain));
  return element;
}

function deviceRow(device) {
  const item = document.createElement("li");
  const head = document.createElement("div");
  head.className = "device-head";

  const name = document.createElement("span");
  name.className = "device-name";
  name.textContent = device.name;

  const state = document.createElement("span");
  state.className = "device-state";
  if (!device.enabled) {
    state.classList.add("disabled");
    state.textContent = t("disabled");
  } else if (device.online) {
    state.classList.add("online");
    state.textContent = t("online");
  } else if (device.last_handshake) {
    state.textContent = t("last_seen", { when: when(device.last_handshake * 1000) });
  } else {
    state.textContent = t("never");
  }

  const address = document.createElement("span");
  address.className = "muted small";
  address.dir = "ltr";
  address.textContent = device.address;
  head.append(name, state, address);

  const traffic = document.createElement("div");
  traffic.className = "muted small";
  traffic.textContent = t("traffic", { received: size(device.received), sent: size(device.sent) });

  const actions = document.createElement("div");
  actions.className = "device-actions";
  actions.append(
    button(t("show"), "quiet", () => showDevice(device.name)),
    button(t(device.enabled ? "disable" : "enable"), "quiet", async () => {
      await api("POST", `/api/devices/${device.name}/${device.enabled ? "disable" : "enable"}`);
      await refresh();
    }),
    button(t("remove"), "danger", async () => {
      if (!confirm(t("confirm_remove", { name: device.name }))) return;
      await api("DELETE", `/api/devices/${device.name}`);
      await refresh();
    }),
  );
  item.append(head, traffic, actions);
  return item;
}

function showDevicePayload(payload) {
  $("dialog-name").textContent = payload.name;
  $("dialog-qr").src = payload.qr;
  $("dialog-config").textContent = payload.config;
  const link = $("dialog-download");
  link.href = `/api/devices/${payload.name}/config`;
  link.download = `${payload.name}.conf`;
  $("device-dialog").showModal();
}

async function showDevice(name) {
  showDevicePayload(await api("GET", `/api/devices/${name}`));
}

async function refresh() {
  const state = await api("GET", "/api/state");
  $("login").hidden = true;
  $("app").hidden = false;
  $("logout").hidden = false;
  $("server").textContent = t("server_line", state.server);
  $("version").textContent = `ByteGuard ${state.version}`;
  $("devices").replaceChildren(...state.devices.map(deviceRow));
  $("empty").hidden = state.devices.length > 0;

  const last = state.backup.last;
  $("backup-last").textContent = last ? t("backup_last", { when: when(last.made_at) }) : t("backup_none");
  $("telegram-state").textContent = t(state.backup.telegram ? "telegram_on" : "telegram_not_set");
  $("telegram-off").hidden = !state.backup.telegram;
  $("telegram-form").hidden = state.backup.telegram;
}

function reportBackup(results) {
  const failed = Object.entries(results).find(([, result]) => !result.ok);
  if (failed) notify(t("backup_failed", { destination: failed[0], error: failed[1].error }), true);
  else notify(t("backup_done"));
}

function start() {
  clearInterval(timer);
  timer = setInterval(() => refresh().catch(explain), 5000);
  return refresh();
}

$("language").addEventListener("click", async () => {
  language = language === "ar" ? "en" : "ar";
  localStorage.setItem("byteguard-language", language);
  await loadLanguage();
  if (!$("app").hidden) refresh().catch(explain);
});

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("POST", "/api/login", { password: $("password").value });
    $("password").value = "";
    notify("");
    await start();
  } catch (error) {
    explain(error);
  }
});

$("logout").addEventListener("click", async () => {
  await api("POST", "/api/logout").catch(() => {});
  showLogin();
});

$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("POST", "/api/devices", { name: $("new-name").value.trim() });
    $("new-name").value = "";
    notify("");
    showDevicePayload(payload);
    await refresh();
  } catch (error) {
    explain(error);
  }
});

$("backup-now").addEventListener("click", async () => {
  try {
    reportBackup(await api("POST", "/api/backup"));
    await refresh();
  } catch (error) {
    explain(error);
  }
});

$("telegram-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("POST", "/api/backup/telegram", { token: $("telegram-token").value.trim() });
    if (result.connected) {
      $("telegram-token").value = "";
      notify(t("telegram_connected", { chat: result.chat }));
      await refresh();
    } else {
      notify(t("telegram_waiting", { bot: result.bot }));
    }
  } catch (error) {
    explain(error);
  }
});

$("telegram-off").addEventListener("click", async () => {
  try {
    await api("DELETE", "/api/backup/telegram");
    await refresh();
  } catch (error) {
    explain(error);
  }
});

$("dialog-close").addEventListener("click", () => $("device-dialog").close());

loadLanguage().then(() => start().catch(explain));
