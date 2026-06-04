# 🗂️ 项目待办清单

> 按优先级从高到低排列。完成项请勾选并记录完成日期。

---

## 🔴 P0 — 阻塞上线

- [ ] **单元测试覆盖**
  - 为 `TelegramWebSkill` 和 `WhatsAppWebSkill` 的核心方法编写测试
  - 使用 `pytest` + `pytest-asyncio`
  - 关键路径：登录检查、聊天列表获取、消息发送、搜索
  - 挑战：Playwright 操作需要 mock 或集成测试

- [ ] **DOM 选择器抽象层**
  - 问题：Telegram/WhatsApp 前端更新会导致选择器失效
  - 方案：将选择器集中管理，支持多版本回退
  - 例如：`SELECTORS["v2.1"]` → `SELECTORS["v2.2"]` 自动降级

---

## 🟡 P1 — 重要改进

- [ ] **错误重试 + 降级机制**
  - 操作失败时自动重试 3 次（指数退避）
  - 失败时自动截图保存到 `data/debug/`
  - 发送消息失败时提供降级方案（如提示用户手动操作）

- [ ] **结构化日志系统**
  - 替换所有 `print()` 为 `logging`
  - 支持日志级别（DEBUG/INFO/WARNING/ERROR）
  - 日志轮转（每天一个文件，保留 7 天）
  - 统一日志格式：`[timestamp] [level] [module] message`

- [ ] **并发安全**
  - 全局单例 `_skill` 没有考虑多线程/多进程并发
  - 方案：使用 `asyncio.Lock` 保护关键操作，或改用连接池

- [ ] **Health Check Endpoint**
  - MCP Server 启动时暴露健康检查接口
  - 检查项：浏览器连接、登录状态、网络连通性
  - 便于监控和告警

---

## 🟢 P2 — 体验优化

- [ ] **Docker 化**
  - 编写 Dockerfile，支持一键部署
  - 挂载 `data/` 目录持久化登录态
  - 环境变量配置（替换硬编码路径）

- [ ] **配置热重载**
  - 支持通过文件或环境变量动态修改配置
  - 无需重启服务即可生效

- [ ] **WhatsApp 首次登录向导**
  - 当前需要手动运行 `demo.py` 扫码
  - 方案：MCP Server 启动时检测到未登录，自动打开有头浏览器引导用户扫码

- [ ] **Telegram + WhatsApp 统一工具前缀**
  - 当前两个 MCP Server 独立运行，工具名可能冲突
  - 方案：统一为 `telegram_get_chat_list`、`whatsapp_get_chat_list`

---

## 🔵 P3 — 技术债

- [ ] **代码去重**
  - `TelegramWebSkill` 和 `WhatsAppWebSkill` 有大量重复代码（`_is_any_visible`、`_find_first_visible`、数据类定义等）
  - 方案：提取 `BaseWebSkill` 抽象基类

- [ ] **类型检查（mypy）**
  - 当前代码有类型注解但不严格
  - 添加 `mypy` 检查到 CI

- [ ] **CI/CD 流水线**
  - GitHub Actions：代码检查、测试、打包
  - 自动发布到 PyPI（可选）

---

## 📊 当前状态速览

| 维度 | 状态 | 备注 |
|------|------|------|
| 功能完整性 | ✅ MVP | 20 个 MCP 工具，双平台支持 |
| 代码质量 | ⚠️ 需改进 | 无测试，有重复代码 |
| 生产就绪 | ❌ 不建议 | 缺少监控、重试、日志 |
| 文档 | ✅ 完善 | README + DEPLOY + TODO |

---

## 🎯 下一阶段目标

建议先完成 **P0**（测试 + 选择器抽象），使项目达到"可维护"状态。然后推进 **P1**（日志 + 重试 + 并发安全），达到"可依赖"状态。

欢迎认领任务！在对应项后加上 `@your-name` 即可。
