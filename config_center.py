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

from src.config import CONFIG_FILE, get_app_config, get_config_schema, reset_app_config, save_app_config
from src.moonshot_api import get_curated_models, list_models, validate_api_key


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
      setMessage("配置已加载", "ok");
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

    loadConfig();
  </script>
</body>
</html>
"""


class ConfigCenterHandler(BaseHTTPRequestHandler):
    """配置中心 HTTP 处理器"""

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send_html(HTML_PAGE)

        if self.path == "/api/config":
            payload = {
                "config": get_app_config(),
                "schema": get_config_schema(),
                "config_file": str(CONFIG_FILE),
                "model_catalog": get_curated_models(),
            }
            return self._send_json(payload)

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
