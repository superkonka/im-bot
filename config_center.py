#!/usr/bin/env python3
"""
本地配置中心

用法:
  python config_center.py
  python config_center.py --host 127.0.0.1 --port 8765
"""
import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from src.config import CONFIG_FILE, get_app_config, get_config_schema, reset_app_config, save_app_config
from src.moonshot_api import get_curated_models, list_models, validate_api_key
from src.runtime_control import OperatorControlStore, RuntimeDashboardStore, get_runtime_store_paths
from src.telegram_userbot import TelegramUserSettings, fetch_recent_dialog_choices


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>IM Bot 配置中心</title>
  <style>
    :root {
      --bg: #f4efe7;
      --panel: #fffaf4;
      --ink: #1d2a33;
      --muted: #667784;
      --line: #d8cfc4;
      --accent: #0d8f6f;
      --accent-2: #d87b35;
      --danger: #c34b37;
      --shadow: 0 18px 40px rgba(29, 42, 51, 0.08);
      --radius: 18px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Pro Display", "PingFang SC", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(216, 123, 53, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(13, 143, 111, 0.14), transparent 34%),
        var(--bg);
    }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px 1fr;
    }
    .sidebar {
      border-right: 1px solid rgba(29, 42, 51, 0.08);
      padding: 28px 20px;
      background: rgba(255, 250, 244, 0.82);
      backdrop-filter: blur(18px);
      position: sticky;
      top: 0;
      height: 100vh;
    }
    .brand {
      margin-bottom: 22px;
    }
    .brand h1 {
      margin: 0 0 8px;
      font-size: 26px;
      line-height: 1.1;
    }
    .brand p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }
    .path-box, .status-box {
      padding: 12px 14px;
      background: rgba(255,255,255,0.75);
      border: 1px solid rgba(29,42,51,0.08);
      border-radius: 14px;
      margin-bottom: 14px;
      font-size: 13px;
      color: var(--muted);
      word-break: break-all;
    }
    .nav {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 18px;
    }
    .nav button {
      border: 1px solid transparent;
      background: transparent;
      color: var(--ink);
      padding: 12px 14px;
      border-radius: 14px;
      text-align: left;
      cursor: pointer;
      transition: 0.2s ease;
      font-size: 14px;
    }
    .nav button:hover,
    .nav button.active {
      background: rgba(13, 143, 111, 0.09);
      border-color: rgba(13, 143, 111, 0.22);
      transform: translateX(2px);
    }
    .main {
      padding: 30px;
    }
    .toolbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }
    .toolbar button {
      border: none;
      border-radius: 999px;
      padding: 12px 18px;
      cursor: pointer;
      font-size: 14px;
      color: white;
      box-shadow: var(--shadow);
    }
    .toolbar .save { background: var(--accent); }
    .toolbar .reload { background: #40617a; }
    .toolbar .reset { background: var(--danger); }
    .panel {
      background: rgba(255, 250, 244, 0.92);
      border: 1px solid rgba(29, 42, 51, 0.08);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 24px;
    }
    .section-title {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }
    .section-title h2 {
      margin: 0;
      font-size: 24px;
    }
    .section-title p {
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.6;
    }
    .subsection {
      margin-top: 24px;
      padding-top: 12px;
      border-top: 1px solid rgba(29, 42, 51, 0.08);
    }
    .subsection h3 {
      margin: 0 0 14px;
      font-size: 18px;
    }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }
    .field {
      background: rgba(255,255,255,0.76);
      border: 1px solid rgba(29,42,51,0.08);
      border-radius: 16px;
      padding: 14px;
    }
    .field label {
      display: block;
      font-weight: 700;
      margin-bottom: 8px;
      font-size: 14px;
    }
    .field .hint {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 10px;
      min-height: 38px;
    }
    .field input,
    .field select,
    .field textarea {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      padding: 10px 12px;
      font-size: 14px;
      color: var(--ink);
    }
    .field textarea {
      min-height: 130px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .field input[type="checkbox"] {
      width: auto;
      transform: scale(1.1);
      margin-right: 8px;
    }
    .check-row {
      display: flex;
      align-items: center;
      min-height: 42px;
    }
    .message {
      margin-top: 10px;
      font-size: 13px;
      color: var(--muted);
    }
    .api-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
      align-items: center;
    }
    .api-tools button {
      border: none;
      border-radius: 999px;
      padding: 10px 16px;
      cursor: pointer;
      font-size: 14px;
      color: white;
      background: var(--accent-2);
      box-shadow: var(--shadow);
    }
    .api-tools button.secondary {
      background: #56718b;
    }
    .api-status {
      width: 100%;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.6;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.76);
      border: 1px solid rgba(29,42,51,0.08);
    }
    .api-status strong {
      color: var(--ink);
    }
    .api-status.ok strong {
      color: var(--accent);
    }
    .api-status.err strong {
      color: var(--danger);
    }
    .ok { color: var(--accent); }
    .err { color: var(--danger); }
    .runtime-card {
      background: rgba(255,255,255,0.76);
      border: 1px solid rgba(29,42,51,0.08);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .runtime-card input,
    .runtime-card textarea {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      padding: 10px 12px;
      font-size: 14px;
      color: var(--ink);
      margin-top: 12px;
    }
    .runtime-card textarea {
      min-height: 120px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .runtime-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 12px 0 0;
    }
    .runtime-actions button {
      border: none;
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      font-size: 13px;
      color: white;
      background: var(--accent);
    }
    .runtime-actions button.secondary {
      background: #56718b;
    }
    .runtime-actions button.danger {
      background: var(--danger);
    }
    .runtime-list {
      display: grid;
      gap: 10px;
    }
    .runtime-item {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(29,42,51,0.08);
      font-size: 14px;
      line-height: 1.6;
    }
    .runtime-item strong {
      display: inline-block;
      min-width: 54px;
    }
    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      .sidebar {
        position: static;
        height: auto;
        border-right: none;
        border-bottom: 1px solid rgba(29, 42, 51, 0.08);
      }
      .main { padding: 20px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <h1>配置中心</h1>
        <p>按分类查看、编辑、保存。配置文件是结构化 JSON，适合人和 LLM 同时读写。</p>
      </div>
      <div class="path-box" id="configPath">配置文件: 加载中...</div>
      <div class="status-box" id="statusBox">状态: 等待加载</div>
      <div class="nav" id="nav"></div>
    </aside>
    <main class="main">
      <div class="toolbar">
        <button class="save" onclick="saveConfig()">保存配置</button>
        <button class="reload" onclick="loadConfig()">重新加载</button>
        <button class="reset" onclick="resetConfig()">恢复默认</button>
      </div>
      <section class="panel">
        <div class="section-title">
          <div>
            <h2 id="sectionTitle">加载中...</h2>
            <p id="sectionDesc"></p>
          </div>
          <div class="message" id="message"></div>
        </div>
        <div id="content"></div>
      </section>
    </main>
  </div>

  <script>
    let state = {
      config: null,
      schema: null,
      active: null,
      modelCatalog: [],
      dynamicOptions: {},
      apiStatus: null,
      runtime: null,
      runtimeTargets: [],
      runtimeTargetsError: "",
    };

    function setMessage(text, cls = "") {
      const el = document.getElementById("message");
      el.textContent = text || "";
      el.className = "message " + cls;
      document.getElementById("statusBox").textContent = "状态: " + (text || "空闲");
    }

    function parseJsonInput(text, fallback) {
      if (text.trim() === "") return fallback;
      return JSON.parse(text);
    }

    function registerModelOptions(models) {
      const options = (models || []).map(item => item.id).filter(Boolean);
      state.dynamicOptions["api.kimi_vision_model"] = options;
      state.dynamicOptions["api.kimi_text_model"] = options;
    }

    function getInputValue(input) {
      const kind = input.dataset.kind;
      if (kind === "boolean") return input.checked;
      if (kind === "integer") return parseInt(input.value || "0", 10);
      if (kind === "float") return parseFloat(input.value || "0");
      if (kind === "json") return parseJsonInput(input.value, null);
      return input.value;
    }

    function inputForField(path, fieldSchema, value) {
      const field = document.createElement("div");
      field.className = "field";

      const label = document.createElement("label");
      label.textContent = fieldSchema.label || path;
      field.appendChild(label);

      const hint = document.createElement("div");
      hint.className = "hint";
      hint.textContent = fieldSchema.description || "";
      field.appendChild(hint);

      const key = "field::" + path;

      if (fieldSchema.type === "boolean") {
        const row = document.createElement("div");
        row.className = "check-row";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = !!value;
        input.dataset.path = path;
        input.dataset.kind = "boolean";
        input.id = key;
        const text = document.createElement("span");
        text.textContent = value ? "已启用" : "已关闭";
        input.addEventListener("change", () => {
          text.textContent = input.checked ? "已启用" : "已关闭";
        });
        row.appendChild(input);
        row.appendChild(text);
        field.appendChild(row);
        return field;
      }

      let input;
      const dynamicOptions = state.dynamicOptions[path] || [];
      if (fieldSchema.type === "enum" || dynamicOptions.length) {
        input = document.createElement("select");
        const options = dynamicOptions.length ? dynamicOptions : (fieldSchema.options || []);
        const finalOptions = options.includes(value) || value === "" || value == null
          ? options
          : [value, ...options];
        for (const option of finalOptions) {
          const item = document.createElement("option");
          item.value = option;
          item.textContent = option;
          if (option === value) item.selected = true;
          input.appendChild(item);
        }
      } else if (fieldSchema.type === "json") {
        input = document.createElement("textarea");
        input.value = JSON.stringify(value, null, 2);
      } else {
        input = document.createElement("input");
        input.type = fieldSchema.secret ? "password" : "text";
        input.value = value ?? "";
      }

      input.dataset.path = path;
      input.dataset.kind = fieldSchema.type || "string";
      input.id = key;
      field.appendChild(input);
      return field;
    }

    function getByPath(obj, path) {
      return path.split(".").reduce((acc, key) => acc[key], obj);
    }

    function setByPath(obj, path, value) {
      const keys = path.split(".");
      const last = keys.pop();
      let cursor = obj;
      for (const key of keys) {
        if (!(key in cursor)) cursor[key] = {};
        cursor = cursor[key];
      }
      cursor[last] = value;
    }

    function buildFieldGrid(fields, basePath, data) {
      const grid = document.createElement("div");
      grid.className = "field-grid";
      for (const [fieldKey, fieldSchema] of Object.entries(fields)) {
        grid.appendChild(inputForField(basePath + "." + fieldKey, fieldSchema, data[fieldKey]));
      }
      return grid;
    }

    function getDraftValue(path, fallback = "") {
      const input = document.querySelector(`[data-path="${path}"]`);
      return input ? getInputValue(input) : fallback;
    }

    function renderApiTools(container) {
      const wrapper = document.createElement("div");
      wrapper.className = "api-tools";

      const validateButton = document.createElement("button");
      validateButton.textContent = "验证 Key 并刷新模型";
      validateButton.onclick = validateApiAndFetchModels;
      wrapper.appendChild(validateButton);

      const fetchButton = document.createElement("button");
      fetchButton.className = "secondary";
      fetchButton.textContent = "仅刷新模型列表";
      fetchButton.onclick = fetchLatestModels;
      wrapper.appendChild(fetchButton);

      const status = document.createElement("div");
      status.className = "api-status";

      if (!state.apiStatus) {
        status.innerHTML = "<strong>尚未验证</strong><br>填入 API Key 后，点击“验证 Key 并刷新模型”，配置中心会请求 Moonshot API 拉取当前可用模型。";
      } else {
        status.classList.add(state.apiStatus.valid ? "ok" : "err");
        const lines = [
          `<strong>${state.apiStatus.valid ? "Key 验证成功" : "Key 验证失败"}</strong>`,
          state.apiStatus.message || "",
        ];
        if (state.apiStatus.modelCount != null) {
          lines.push(`模型数量: ${state.apiStatus.modelCount}`);
        }
        if (state.apiStatus.source) {
          lines.push(`模型来源: ${state.apiStatus.source}`);
        }
        status.innerHTML = lines.filter(Boolean).join("<br>");
      }

      wrapper.appendChild(status);
      container.appendChild(wrapper);
    }

    async function validateApiAndFetchModels() {
      try {
        setMessage("正在验证 Key 并拉取模型...");
        const response = await fetch("/api/validate-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: getDraftValue("api.kimi_api_key", ""),
            base_url: getDraftValue("api.kimi_base_url", ""),
          }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "验证失败");

        state.apiStatus = {
          valid: payload.valid,
          message: payload.message,
          source: payload.source,
          modelCount: (payload.models || []).length,
        };

        if (payload.valid) {
          state.modelCatalog = payload.models || [];
          registerModelOptions(state.modelCatalog);
          renderSection(state.active);
          setMessage("Key 验证成功，模型列表已刷新", "ok");
          return;
        }

        renderSection(state.active);
        setMessage(payload.message || "Key 验证失败", "err");
      } catch (error) {
        state.apiStatus = { valid: false, message: error.message, source: "error" };
        renderSection(state.active);
        setMessage("验证失败: " + error.message, "err");
      }
    }

    async function fetchLatestModels() {
      try {
        setMessage("正在拉取最新模型...");
        const response = await fetch("/api/fetch-models", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: getDraftValue("api.kimi_api_key", ""),
            base_url: getDraftValue("api.kimi_base_url", ""),
          }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "拉取失败");

        state.modelCatalog = payload.models || [];
        registerModelOptions(state.modelCatalog);
        state.apiStatus = {
          valid: true,
          message: payload.message,
          source: payload.source,
          modelCount: state.modelCatalog.length,
        };
        renderSection(state.active);
        setMessage("模型列表已刷新", "ok");
      } catch (error) {
        state.apiStatus = { valid: false, message: error.message, source: "error" };
        renderSection(state.active);
        setMessage("拉取模型失败: " + error.message, "err");
      }
    }

    function renderSection(sectionKey) {
      state.active = sectionKey;
      document.querySelectorAll(".nav button").forEach(button => {
        button.classList.toggle("active", button.dataset.section === sectionKey);
      });

      if (sectionKey === "runtime") {
        return renderRuntimeSection();
      }

      const section = state.schema[sectionKey];
      const data = state.config[sectionKey];
      document.getElementById("sectionTitle").textContent = section.title || sectionKey;
      document.getElementById("sectionDesc").textContent = section.description || "";

      const content = document.getElementById("content");
      content.innerHTML = "";

      if (sectionKey === "api") {
        renderApiTools(content);
      }

      if (section.fields) {
        content.appendChild(buildFieldGrid(section.fields, sectionKey, data));
      }

      if (section.subsections) {
        for (const [subKey, subSchema] of Object.entries(section.subsections)) {
          const box = document.createElement("div");
          box.className = "subsection";
          const title = document.createElement("h3");
          title.textContent = subSchema.title || subKey;
          box.appendChild(title);
          box.appendChild(buildFieldGrid(subSchema.fields, sectionKey + "." + subKey, data[subKey]));
          content.appendChild(box);
        }
      }
    }

    function renderRuntimeSection() {
      document.getElementById("sectionTitle").textContent = "运行后台";
      document.getElementById("sectionDesc").textContent = "查看 Telegram 运行状态、最近消息和待审核草稿，并进行暂停/恢复或人工审批。";

      const content = document.getElementById("content");
      content.innerHTML = "";

      if (!state.runtime) {
        const empty = document.createElement("div");
        empty.className = "runtime-card";
        empty.textContent = "尚未读取到运行时数据。";
        content.appendChild(empty);
        return;
      }

      const runtime = state.runtime.runtime || {};
      const control = state.runtime.control || {};
      const isWebRuntime = (runtime.transport || "") === "web";

      const summary = document.createElement("div");
      summary.className = "runtime-card";
      summary.innerHTML = `
        <div><strong>状态:</strong> ${runtime.status || "idle"}</div>
        <div><strong>运行模式:</strong> ${runtime.transport || "-"}</div>
        <div><strong>Session:</strong> ${runtime.session_name || "-"}</div>
        <div><strong>目标聊天:</strong> ${runtime.target_chat || "-"}</div>
        <div><strong>锁定模式:</strong> ${runtime.lock_mode || "-"}</div>
        <div><strong>锁定状态:</strong> ${runtime.locked ? "已锁定" : "未锁定"}</div>
        <div><strong>当前锁定聊天:</strong> ${runtime.locked_chat_title || "-"}</div>
        <div><strong>最近锁定时间:</strong> ${runtime.last_locked_at || "-"}</div>
        <div><strong>聊天记忆摘要:</strong> ${runtime.memory_summary || "-"}</div>
        <div><strong>记忆文件:</strong> ${runtime.memory_file || "-"}</div>
        <div><strong>自动化暂停:</strong> ${control.automation_paused ? "是" : "否"}</div>
        <div><strong>主动聊天暂停:</strong> ${control.proactive_paused ? "是" : "否"}</div>
        <div><strong>人工审核:</strong> ${runtime.manual_review_enabled ? "开启" : "关闭"}</div>
        <div><strong>最后决策:</strong> ${runtime.last_decision || "-"}</div>
        <div><strong>最后错误:</strong> ${runtime.last_error || "-"}</div>
        <div><strong>调试轨迹文件:</strong> ${runtime.debug_trace_file || "-"}</div>
        <div><strong>最近节点轨迹:</strong> ${runtime.last_step_trace || "-"}</div>
      `;

      const summaryActions = document.createElement("div");
      summaryActions.className = "runtime-actions";
      const pauseButton = document.createElement("button");
      pauseButton.className = control.automation_paused ? "secondary" : "danger";
      pauseButton.textContent = control.automation_paused ? "恢复自动化" : "暂停自动化";
      pauseButton.onclick = () => setRuntimePause("automation", !control.automation_paused);
      summaryActions.appendChild(pauseButton);

      const proactiveButton = document.createElement("button");
      proactiveButton.className = control.proactive_paused ? "secondary" : "danger";
      proactiveButton.textContent = control.proactive_paused ? "恢复主动聊天" : "暂停主动聊天";
      proactiveButton.onclick = () => setRuntimePause("proactive", !control.proactive_paused);
      summaryActions.appendChild(proactiveButton);
      if (!isWebRuntime) {
        summary.appendChild(summaryActions);
      }
      content.appendChild(summary);

      if (isWebRuntime) {
        const lockCard = document.createElement("div");
        lockCard.className = "runtime-card";
        lockCard.innerHTML = `
          <div><strong>Web 锁定聊天状态</strong></div>
          <div class="message">当前 Web 模式不会通过后台远程切换聊天。请在 Telegram Web 中手动打开目标聊天，系统会识别并锁定当前窗口。</div>
        `;
        const lockActions = document.createElement("div");
        lockActions.className = "runtime-actions";
        const clearMemoryButton = document.createElement("button");
        clearMemoryButton.className = "secondary";
        clearMemoryButton.textContent = "清空当前聊天记忆";
        clearMemoryButton.onclick = async () => {
          if (!confirm("确定清空当前锁定聊天的本地记忆吗？这不会删除 Telegram 聊天记录。")) return;
          await clearRuntimeMemory();
        };
        lockActions.appendChild(clearMemoryButton);
        lockCard.appendChild(lockActions);
        content.appendChild(lockCard);
      }

      if (isWebRuntime) {
        const messagesCard = document.createElement("div");
        messagesCard.className = "runtime-card";
        const title = document.createElement("h3");
        title.textContent = "最近消息";
        messagesCard.appendChild(title);

        const list = document.createElement("div");
        list.className = "runtime-list";
        const recentMessages = runtime.recent_messages || [];
        if (!recentMessages.length) {
          const item = document.createElement("div");
          item.className = "runtime-item";
          item.textContent = "暂无最近消息。";
          list.appendChild(item);
        } else {
          recentMessages.slice().reverse().forEach(message => {
            const item = document.createElement("div");
            item.className = "runtime-item";
            item.innerHTML = `<strong>${message.role || "-"}</strong> ${message.timestamp || ""}<br>${message.text || ""}`;
            list.appendChild(item);
          });
        }
        messagesCard.appendChild(list);
        content.appendChild(messagesCard);
        return;
      }

      const switchCard = document.createElement("div");
      switchCard.className = "runtime-card";
      switchCard.innerHTML = `
        <div><strong>切换目标聊天</strong></div>
        <div class="message">支持输入用户名、数值 ID，或直接点击最近聊天候选。候选只作为快捷入口，最终仍会解析到实际聊天对象。</div>
      `;
      const targetInput = document.createElement("input");
      targetInput.type = "text";
      targetInput.id = "runtimeTargetInput";
      targetInput.placeholder = "输入 @username、数值 ID 或当前 target_chat 文本";
      targetInput.value = runtime.target_chat || "";
      switchCard.appendChild(targetInput);

      const switchActions = document.createElement("div");
      switchActions.className = "runtime-actions";
      const switchButton = document.createElement("button");
      switchButton.textContent = "提交切换";
      switchButton.onclick = async () => {
        const nextTarget = targetInput.value.trim();
        if (!nextTarget) return;
        await switchRuntimeTarget(nextTarget);
      };
      switchActions.appendChild(switchButton);
      const refreshTargetsButton = document.createElement("button");
      refreshTargetsButton.className = "secondary";
      refreshTargetsButton.textContent = "刷新候选";
      refreshTargetsButton.onclick = async () => {
        await loadRuntimeTargets(true);
        renderSection("runtime");
      };
      switchActions.appendChild(refreshTargetsButton);
      switchCard.appendChild(switchActions);

      if (state.runtimeTargetsError) {
        const errorText = document.createElement("div");
        errorText.className = "message err";
        errorText.textContent = "读取最近聊天失败: " + state.runtimeTargetsError;
        switchCard.appendChild(errorText);
      } else if ((state.runtimeTargets || []).length) {
        const targetChoices = document.createElement("div");
        targetChoices.className = "runtime-actions";
        state.runtimeTargets.forEach(choice => {
          const button = document.createElement("button");
          button.className = "secondary";
          button.textContent = choice.display_label || choice.target_value;
          button.onclick = () => {
            targetInput.value = choice.target_value;
          };
          targetChoices.appendChild(button);
        });
        switchCard.appendChild(targetChoices);
      } else {
        const emptyChoices = document.createElement("div");
        emptyChoices.className = "message";
        emptyChoices.textContent = "还没有加载到最近聊天候选，可以点“刷新候选”读取。";
        switchCard.appendChild(emptyChoices);
      }
      content.appendChild(switchCard);

      const manualSendCard = document.createElement("div");
      manualSendCard.className = "runtime-card";
      manualSendCard.innerHTML = `
        <div><strong>人工接管发送</strong></div>
        <div class="message">这条消息会直接作为后台命令交给 bot 发送，适合人工兜底、补一句话或临时接管当前聊天。</div>
      `;
      const manualSendInput = document.createElement("textarea");
      manualSendInput.id = "runtimeManualSendInput";
      manualSendInput.placeholder = "输入要发送给当前目标聊天的内容";
      manualSendCard.appendChild(manualSendInput);
      const manualSendActions = document.createElement("div");
      manualSendActions.className = "runtime-actions";
      const manualSendButton = document.createElement("button");
      manualSendButton.textContent = "发送给当前聊天";
      manualSendButton.onclick = async () => {
        const message = manualSendInput.value.trim();
        if (!message) {
          setMessage("手动发送内容不能为空", "err");
          return;
        }
        await submitManualSend(message);
        manualSendInput.value = "";
      };
      manualSendActions.appendChild(manualSendButton);
      manualSendCard.appendChild(manualSendActions);
      content.appendChild(manualSendCard);

      const draftCard = document.createElement("div");
      draftCard.className = "runtime-card";
      const draft = runtime.pending_draft;
      if (draft) {
        draftCard.innerHTML = `
          <div><strong>待审模式:</strong> ${draft.mode || "-"}</div>
          <div><strong>话题:</strong> ${draft.topic || "-"}</div>
          <div><strong>风险:</strong> ${draft.risk || "-"}</div>
          <div><strong>置信度:</strong> ${draft.confidence ?? "-"}</div>
          <div><strong>原因:</strong> ${draft.reason || "-"}</div>
          <div><strong>消息:</strong> ${draft.message || "-"}</div>
        `;
        const draftActions = document.createElement("div");
        draftActions.className = "runtime-actions";

        const approveButton = document.createElement("button");
        approveButton.textContent = "批准发送";
        approveButton.onclick = async () => {
          const edited = window.prompt("可选：修改后发送。直接确定表示按原文发送。", draft.message || "");
          if (edited === null) return;
          await submitDraftAction("approve", draft.draft_id, edited);
        };
        draftActions.appendChild(approveButton);

        const rejectButton = document.createElement("button");
        rejectButton.className = "danger";
        rejectButton.textContent = "驳回草稿";
        rejectButton.onclick = () => submitDraftAction("reject", draft.draft_id, "");
        draftActions.appendChild(rejectButton);

        draftCard.appendChild(draftActions);
      } else {
        draftCard.textContent = "当前没有待审核草稿。";
      }
      content.appendChild(draftCard);

      const messagesCard = document.createElement("div");
      messagesCard.className = "runtime-card";
      const title = document.createElement("h3");
      title.textContent = "最近消息";
      messagesCard.appendChild(title);

      const list = document.createElement("div");
      list.className = "runtime-list";
      const recentMessages = runtime.recent_messages || [];
      if (!recentMessages.length) {
        const item = document.createElement("div");
        item.className = "runtime-item";
        item.textContent = "暂无最近消息。";
        list.appendChild(item);
      } else {
        recentMessages.slice().reverse().forEach(message => {
          const item = document.createElement("div");
          item.className = "runtime-item";
          item.innerHTML = `<strong>${message.role || "-"}</strong> ${message.timestamp || ""}<br>${message.text || ""}`;
          list.appendChild(item);
        });
      }
      messagesCard.appendChild(list);
      content.appendChild(messagesCard);
    }

    function collectConfigFromForm() {
      const nextConfig = JSON.parse(JSON.stringify(state.config));
      document.querySelectorAll("[data-path]").forEach(input => {
        setByPath(nextConfig, input.dataset.path, getInputValue(input));
      });
      return nextConfig;
    }

    async function loadConfig() {
      setMessage("正在加载配置...");
      const response = await fetch("/api/config");
      const payload = await response.json();
      state.config = payload.config;
      state.schema = payload.schema;
      state.modelCatalog = payload.model_catalog || [];
      registerModelOptions(state.modelCatalog);
      document.getElementById("configPath").textContent = "配置文件: " + payload.config_file;

      const nav = document.getElementById("nav");
      nav.innerHTML = "";
      Object.entries(state.schema).forEach(([key, section], index) => {
        const button = document.createElement("button");
        button.textContent = section.title || key;
        button.dataset.section = key;
        button.onclick = () => renderSection(key);
        nav.appendChild(button);
        if ((state.active && state.active === key) || (!state.active && index === 0)) {
          renderSection(key);
        }
      });

      const runtimeButton = document.createElement("button");
      runtimeButton.textContent = "运行后台";
      runtimeButton.dataset.section = "runtime";
      runtimeButton.onclick = async () => {
        await loadRuntime();
        await loadRuntimeTargets(true);
        renderSection("runtime");
      };
      nav.appendChild(runtimeButton);
      setMessage("配置已加载", "ok");
    }

    async function loadRuntime() {
      try {
        const response = await fetch("/api/runtime");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "加载运行时数据失败");
        state.runtime = payload;
      } catch (error) {
        state.runtime = {
          runtime: { status: "error", last_error: error.message, recent_messages: [] },
          control: { automation_paused: false },
        };
      }
    }

    async function loadRuntimeTargets(force = false) {
      if (!force && state.runtimeTargets.length) {
        return;
      }
      try {
        const response = await fetch("/api/runtime/targets?limit=12");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "读取最近聊天失败");
        state.runtimeTargets = payload.targets || [];
        state.runtimeTargetsError = "";
      } catch (error) {
        state.runtimeTargets = [];
        state.runtimeTargetsError = error.message;
      }
    }

    async function setRuntimePause(kind, paused) {
      try {
        setMessage(paused ? "正在更新暂停状态..." : "正在恢复运行状态...");
        const response = await fetch("/api/runtime/pause", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind, paused }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "更新暂停状态失败");
        await loadRuntime();
        renderSection("runtime");
        setMessage("运行时控制已更新", "ok");
      } catch (error) {
        setMessage(error.message, "err");
      }
    }

    async function submitDraftAction(action, draftId, message) {
      try {
        setMessage(action === "approve" ? "正在批准草稿..." : "正在驳回草稿...");
        const response = await fetch("/api/runtime/draft", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action,
            draft_id: draftId,
            message,
          }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "草稿操作失败");
        await loadRuntime();
        renderSection("runtime");
        setMessage(action === "approve" ? "草稿已提交批准" : "草稿已提交驳回", "ok");
      } catch (error) {
        setMessage(error.message, "err");
      }
    }

    async function switchRuntimeTarget(targetChat) {
      try {
        setMessage("正在切换目标聊天...");
        const response = await fetch("/api/runtime/target", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_chat: targetChat }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "切换失败");
        await loadRuntime();
        await loadRuntimeTargets(true);
        renderSection("runtime");
        setMessage("目标聊天切换命令已提交", "ok");
      } catch (error) {
        setMessage(error.message, "err");
      }
    }

    async function submitManualSend(message) {
      try {
        setMessage("正在提交人工发送命令...");
        const response = await fetch("/api/runtime/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "人工发送失败");
        await loadRuntime();
        renderSection("runtime");
        setMessage("人工发送命令已提交", "ok");
      } catch (error) {
        setMessage(error.message, "err");
      }
    }

    async function clearRuntimeMemory() {
      try {
        setMessage("正在清空当前聊天记忆...");
        const response = await fetch("/api/runtime/memory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "clear" }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "清空聊天记忆失败");
        await loadRuntime();
        renderSection("runtime");
        setMessage("清空聊天记忆命令已提交", "ok");
      } catch (error) {
        setMessage(error.message, "err");
      }
    }

    async function saveConfig() {
      try {
        setMessage("正在保存配置...");
        const response = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(collectConfigFromForm()),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "保存失败");
        state.config = payload.config;
        renderSection(state.active);
        setMessage("配置已保存", "ok");
      } catch (error) {
        setMessage("保存失败: " + error.message, "err");
      }
    }

    async function resetConfig() {
      if (!confirm("确定恢复默认配置吗？当前修改会被覆盖。")) return;
      try {
        setMessage("正在恢复默认配置...");
        const response = await fetch("/api/reset", { method: "POST" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "恢复失败");
        state.config = payload.config;
        renderSection(state.active || Object.keys(state.schema)[0]);
        setMessage("已恢复默认配置", "ok");
      } catch (error) {
        setMessage("恢复失败: " + error.message, "err");
      }
    }

    loadConfig().then(loadRuntime);
    setInterval(() => {
      if (state.active === "runtime") {
        loadRuntime().then(() => renderSection("runtime"));
      }
    }, 3000);
  </script>
</body>
</html>
"""


class ConfigCenterHandler(BaseHTTPRequestHandler):
    """配置中心 HTTP 处理器"""

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            return self._send_html(HTML_PAGE)

        if parsed.path == "/api/config":
            payload = {
                "config": get_app_config(),
                "schema": get_config_schema(),
                "config_file": str(CONFIG_FILE),
                "model_catalog": get_curated_models(),
            }
            return self._send_json(payload)

        if parsed.path == "/api/runtime":
            dashboard_store, control_store, session_name, target_chat = self._get_active_runtime_bundle()
            dashboard = dashboard_store.load(session_name=session_name, target_chat=target_chat)
            control = control_store.load()
            return self._send_json({
                "runtime": dashboard.__dict__ | {
                    "recent_messages": [item.__dict__ for item in dashboard.recent_messages],
                    "pending_draft": dashboard.pending_draft.__dict__ if dashboard.pending_draft else None,
                },
                "control": {
                    "automation_paused": control.automation_paused,
                    "proactive_paused": control.proactive_paused,
                    "pending_commands": len(control.commands),
                },
            })

        if parsed.path == "/api/runtime/targets":
            try:
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["12"])[0] or 12)
                choices = self._get_runtime_target_choices(limit=max(1, min(limit, 20)))
                return self._send_json({
                    "targets": [
                        {
                            "title": choice.title,
                            "username": choice.username,
                            "dialog_id": choice.dialog_id,
                            "target_value": choice.target_value(),
                            "display_label": choice.display_label(),
                        }
                        for choice in choices
                    ]
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        return self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/config":
            try:
                payload = self._read_json_body()
                saved = save_app_config(payload)
                return self._send_json({"ok": True, "config": saved})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/validate-key":
            try:
                payload = self._read_json_body()
                api_key = payload.get("api_key", "")
                base_url = payload.get("base_url", "")
                result = validate_api_key(api_key=api_key, base_url=base_url)
                result["source"] = "live" if result.get("valid") else "error"
                return self._send_json(result)
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/fetch-models":
            try:
                payload = self._read_json_body()
                api_key = payload.get("api_key", "")
                base_url = payload.get("base_url", "")

                try:
                    models = list_models(api_key=api_key, base_url=base_url)
                    return self._send_json({
                        "ok": True,
                        "models": models,
                        "source": "live",
                        "message": f"在线拉取成功，共 {len(models)} 个模型",
                    })
                except Exception as exc:
                    models = get_curated_models()
                    return self._send_json({
                        "ok": True,
                        "models": models,
                        "source": "curated",
                        "message": f"在线拉取失败，已回退到内置模型目录: {exc}",
                    })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/reset":
            try:
                config = reset_app_config()
                return self._send_json({"ok": True, "config": config})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        if self.path == "/api/runtime/pause":
            try:
                payload = self._read_json_body()
                kind = str(payload.get("kind", "automation")).strip().lower()
                paused = bool(payload.get("paused", False))
                _, control_store = self._get_runtime_stores()
                if kind == "proactive":
                    control = control_store.set_proactive_paused(paused)
                else:
                    control = control_store.set_paused(paused)
                return self._send_json({
                    "ok": True,
                    "automation_paused": control.automation_paused,
                    "proactive_paused": control.proactive_paused,
                })
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/runtime/draft":
            try:
                payload = self._read_json_body()
                action = str(payload.get("action", "")).strip().lower()
                draft_id = str(payload.get("draft_id", "")).strip()
                message = str(payload.get("message", "")).strip()
                _, control_store = self._get_runtime_stores()
                if action == "approve":
                    control_store.append_command(
                        "approve_draft",
                        {"draft_id": draft_id, "message": message},
                    )
                elif action == "reject":
                    control_store.append_command(
                        "reject_draft",
                        {"draft_id": draft_id},
                    )
                else:
                    raise ValueError("不支持的草稿操作")

                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/runtime/target":
            try:
                payload = self._read_json_body()
                target_chat = str(payload.get("target_chat", "")).strip()
                if not target_chat:
                    raise ValueError("target_chat 不能为空")
                _, control_store = self._get_runtime_stores()
                control_store.append_command(
                    "switch_target",
                    {"target_chat": target_chat},
                )
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/runtime/send":
            try:
                payload = self._read_json_body()
                message = str(payload.get("message", "")).strip()
                if not message:
                    raise ValueError("message 不能为空")
                _, control_store = self._get_runtime_stores()
                control_store.append_command("manual_send", {"message": message})
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if self.path == "/api/runtime/memory":
            try:
                payload = self._read_json_body()
                action = str(payload.get("action", "")).strip().lower()
                if action != "clear":
                    raise ValueError("不支持的聊天记忆操作")
                dashboard_store, control_store, session_name, target_chat = self._get_active_runtime_bundle()
                dashboard = dashboard_store.load(session_name=session_name, target_chat=target_chat)
                if dashboard.transport != "web":
                    raise ValueError("当前运行实例不是 Web 模式，暂不支持此操作")
                control_store.append_command("clear_memory", {})
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        return self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def _send_html(self, html: str):
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status: int = HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(raw_body or "{}")

    def _get_runtime_stores(self):
        config = get_app_config()
        session_name = config.get("telegram_user", {}).get("session_name", "telegram_user")
        runtime_path, control_path = get_runtime_store_paths(session_name)
        return RuntimeDashboardStore(runtime_path), OperatorControlStore(control_path)

    def _get_active_runtime_bundle(self):
        config = get_app_config()
        telegram_session = config.get("telegram_user", {}).get("session_name", "telegram_user")
        telegram_target = config.get("telegram_user", {}).get("target_chat", "")

        candidates = []
        for session_name, target_chat in [
            (telegram_session, telegram_target),
            ("telegram_web", config.get("runtime", {}).get("target_chat_name", "")),
        ]:
            runtime_path, control_path = get_runtime_store_paths(session_name)
            mtime = runtime_path.stat().st_mtime if runtime_path.exists() else -1
            candidates.append((mtime, session_name, target_chat, runtime_path, control_path))

        _, session_name, target_chat, runtime_path, control_path = max(candidates, key=lambda item: item[0])
        return (
            RuntimeDashboardStore(runtime_path),
            OperatorControlStore(control_path),
            session_name,
            target_chat,
        )

    def _get_runtime_target_choices(self, limit: int):
        config = get_app_config()
        settings = TelegramUserSettings.from_config(config)
        return fetch_recent_dialog_choices(settings, limit=limit)


def main():
    parser = argparse.ArgumentParser(description="IM Bot 配置中心")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ConfigCenterHandler)
    print(f"配置中心已启动: http://{args.host}:{args.port}")
    print(f"配置文件: {CONFIG_FILE}")
    print("按 Ctrl+C 停止服务")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n配置中心已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
