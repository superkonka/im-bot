#!/usr/bin/env python3
"""
IM 机器人主类
整合浏览器控制、视觉分析和平台适配
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .browser_controller import BrowserController
from .dom_chat_agent import DOMChatAgent, DOMChatMemory, DOMChatMemoryStore
from .vision_agent import KimiVisionAgent, ActionDecision
from .platforms import get_platform, BasePlatform
from .utils.logger import logger
from .utils.helpers import truncate_string
from .config import (
    SCREENSHOT_DIR, DEFAULT_MAX_STEPS, DEFAULT_STEP_DELAY, get_app_config, get_config_center_url
)
from .runtime_control import (
    OperatorControlStore,
    RuntimeDashboard,
    RuntimeDashboardStore,
    get_runtime_store_paths,
)


class IMBot:
    """IM 机器人"""
    
    def __init__(
        self,
        platform: str,
        max_steps: int = DEFAULT_MAX_STEPS,
        step_delay: int = DEFAULT_STEP_DELAY,
        headless: Optional[bool] = None
    ):
        app_config = get_app_config()
        # 配置
        self.platform: BasePlatform = get_platform(platform)
        self.max_steps = max_steps
        self.step_delay = step_delay
        self.login_timeout = app_config["runtime"]["login_timeout"]
        self.target_chat_name = app_config["runtime"].get("target_chat_name", "").strip()
        self.target_chat_prepare_timeout = int(app_config["runtime"].get("target_chat_prepare_timeout", 45))
        self.target_chat_mode = app_config["runtime"].get("target_chat_mode", "search_then_lock")
        self.target_chat_dom_history_limit = int(app_config["runtime"].get("target_chat_dom_history_limit", 10))
        self.target_chat_use_llm = bool(app_config["runtime"].get("target_chat_use_llm", True))
        self.last_seen_incoming_text = ""
        self.last_sent_reply = ""
        self.target_chat_open_failures = 0
        self.max_target_chat_open_failures = 3
        self.manual_target_chat_mode = False
        self.manual_target_chat_prompted = False
        self.locked_chat_title = ""
        self.last_locked_at = ""
        self.chat_memory = DOMChatMemory()
        
        # 组件
        self.browser = BrowserController(headless=headless)
        self.vision = KimiVisionAgent()
        self.dom_chat_agent = DOMChatAgent(platform_name=platform) if self.target_chat_use_llm else None
        self.dom_chat_memory_store = DOMChatMemoryStore(platform_name=platform)
        runtime_path, control_path = get_runtime_store_paths(f"{platform}_web")
        self.runtime_store = RuntimeDashboardStore(runtime_path)
        self.control_store = OperatorControlStore(control_path)
        self.runtime = self.runtime_store.load(
            session_name=f"{platform}_web",
            target_chat=self.target_chat_name,
        )
        self.runtime.transport = "web"
        self.runtime.lock_mode = self.target_chat_mode
        self.runtime.target_chat = self.target_chat_name
        
        # 设置系统提示词
        self.vision.set_system_prompt(self.platform.get_system_prompt())
        
        # 状态
        self.step = 0
        self.is_running = False
        self.session_dir = SCREENSHOT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir.mkdir(exist_ok=True)
        self.debug_trace_path = self.session_dir / "debug_trace.jsonl"
        self.runtime.debug_trace_file = str(self.debug_trace_path)
        
    def start(self) -> None:
        """启动机器人"""
        logger.banner(f"启动 {self.platform.config.name} 机器人")
        
        # 显示配置信息
        logger.info(f"目标网址: {self.platform.config.url}")
        logger.info(f"登录方式: {self.platform.config.login_method}")
        logger.info(f"最大步数: {self.max_steps}")
        logger.info(f"步进延迟: {self.step_delay}s")
        logger.info(f"配置中心 / 运行后台地址: {get_config_center_url()}（需先运行 python config_center.py）")
        self._update_runtime(status="starting")
        
        # 显示提示
        logger.info("使用提示:")
        for tip in self.platform.config.tips:
            logger.info(f"  • {tip}")
        
        try:
            # 初始化
            self._initialize()
            
            # 等待登录
            if not self._wait_for_login():
                logger.error("登录失败，退出")
                return

            if self._should_use_target_chat_flow():
                self._prepare_target_chat()
            
            # 主循环
            self._main_loop()
            
        except KeyboardInterrupt:
            logger.warning("用户中断")
        except Exception as e:
            logger.error(f"运行错误: {e}")
        finally:
            self._update_runtime(status="stopped")
            self.stop()
    
    def stop(self) -> None:
        """停止机器人"""
        logger.info("停止机器人")
        self.is_running = False
        self.browser.close()
        logger.info(f"共运行 {self.step} 步")
    
    def _initialize(self) -> None:
        """初始化浏览器"""
        logger.info("初始化浏览器...")
        self.browser.open(self.platform.config.url, wait=5)
        logger.info("浏览器已打开")
        self._update_runtime(status="running")
    
    def _wait_for_login(self) -> bool:
        """等待用户完成登录"""
        logger.info(f"等待登录 ({self.platform.config.login_method})...")
        logger.info(f"请在 {self.login_timeout} 秒内完成登录")
        
        waited = 0
        check_interval = 5
        
        while waited < self.login_timeout:
            time.sleep(check_interval)
            waited += check_interval
            
            # 截图检查
            screenshot_path = self._take_screenshot("login_check")
            is_logged_in, hint = self.vision.check_login_status(
                screenshot_path, 
                self.platform.config.name
            )
            
            if is_logged_in:
                logger.info(f"✅ 登录成功！({waited}s)")
                return True
            
            if waited % 15 == 0:
                logger.info(f"⏳ 等待登录中... ({waited}/{self.login_timeout}s)")
                logger.info(f"   状态: {hint}")
        
        logger.error(f"登录超时 ({self.login_timeout}s)")
        return False
    
    def _main_loop(self) -> None:
        """主循环"""
        logger.info("开始监控消息...")
        logger.info("按 Ctrl+C 停止")
        
        self.is_running = True
        
        for self.step in range(1, self.max_steps + 1):
            if not self.is_running:
                break
            
            logger.info(f"\n{'─' * 60}")
            logger.info(f"[步骤 {self.step}/{self.max_steps}] {datetime.now().strftime('%H:%M:%S')}")

            if not self._apply_runtime_controls():
                logger.info("后台已暂停 Web 自动化，等待恢复")
                time.sleep(self.step_delay)
                continue
            
            if self._should_use_target_chat_flow():
                result = self._handle_target_chat_step()
                logger.info(f"✅ 结果: {truncate_string(str(result), 80)}")
                time.sleep(self.step_delay)
                continue

            # 1. 截图
            screenshot_path = self._take_screenshot(f"step_{self.step:03d}")
            if not screenshot_path:
                logger.error("截图失败，停止主循环")
                break

            visual_context, dom_payload = self._build_visual_context()
            self._trace(
                "capture",
                {
                    "screenshot_path": screenshot_path,
                    "dom_summary": dom_payload,
                },
            )

            # 2. 决策
            decision = self.vision.analyze_screenshot(screenshot_path, context=visual_context)
            self._trace(
                "vision_analysis",
                {
                    "decision": decision.to_dict(),
                    "vision_debug": self.vision.get_last_analysis_debug(),
                },
            )
            
            logger.info(f"🧠 决策: {truncate_string(decision.reason, 60)}")
            logger.info(f"🎯 操作: {decision.action} {decision.params}")
            self.runtime.last_decision = truncate_string(
                f"{decision.action} {decision.params} / {decision.reason}",
                180,
            )
            
            # 3. 执行
            result = self._execute_decision(decision)
            logger.info(f"✅ 结果: {truncate_string(str(result), 80)}")
            self.runtime.last_decision = truncate_string(
                f"{decision.action} {decision.params} / {decision.reason} -> {result}",
                180,
            )
            self._trace(
                "execution_result",
                {
                    "decision": decision.to_dict(),
                    "result": result,
                    "browser_debug": self.browser.get_last_action_debug(),
                },
            )
            self._update_runtime(error="" if not str(result).startswith("Error:") else str(result))
            
            # 4. 检查是否完成
            if decision.action == 'done':
                logger.info("任务完成")
                break
            
            # 5. 等待
            wait_time = decision.params.get('seconds', self.step_delay)
            if decision.action != 'wait':
                time.sleep(self.step_delay)
    
    def _take_screenshot(self, name: str) -> str:
        """截图"""
        filepath = self.session_dir / f"{name}.png"
        return self.browser.screenshot(str(filepath))
    
    def _execute_decision(self, decision: ActionDecision) -> str:
        """执行决策"""
        action = decision.action
        params = decision.params
        
        handlers = {
            'open': lambda: self.browser.open(
                params.get('url', self.platform.config.url),
                wait=params.get('wait', 3)
            ),
            'click': lambda: self.browser.click(
                params.get('index', 1),
                wait=params.get('wait', 2)
            ),
            'type': lambda: self.browser.type_text(
                params.get('text', ''),
                wait=params.get('wait', 1)
            ),
            'input': lambda: self.browser.input_to_element(
                params.get('index', 1),
                params.get('text', ''),
                wait=params.get('wait', 1)
            ),
            'state': lambda: self._get_state_info(),
            'wait': lambda: self.browser.wait(params.get('seconds', 3)),
            'done': lambda: "任务完成",
        }
        
        handler = handlers.get(action)
        if handler:
            try:
                self._trace(
                    "execution_start",
                    {
                        "action": action,
                        "params": params,
                    },
                )
                return str(handler())
            except Exception as e:
                logger.error(f"执行操作失败: {e}")
                self._trace(
                    "execution_error",
                    {
                        "action": action,
                        "params": params,
                        "error": str(e),
                    },
                )
                return f"Error: {e}"
        else:
            return f"未知操作: {action}"
    
    def _get_state_info(self) -> str:
        """获取页面状态信息"""
        state = self.browser.get_state()
        elements_info = f"共 {len(state.elements)} 个元素"
        clickable = len(state.get_clickable_elements())
        inputs = len(state.get_input_elements())
        return f"{elements_info}, 可点击: {clickable}, 输入框: {inputs}"

    def _prepare_target_chat(self) -> None:
        """登录后准备指定聊天"""
        logger.info(f"指定聊天模式已启用: {self._target_chat_label()}")
        if self.target_chat_mode in {"manual_lock", "current_window_only"} or not self.target_chat_name:
            if self._can_use_current_chat_window():
                self._lock_current_chat_window()
                return

            if self._wait_for_manual_target_chat_selection():
                return

            logger.warning("当前页面还没有进入可聊天窗口")
            return

        if not self._open_target_chat():
            if self._can_use_current_chat_window():
                self._lock_current_chat_window()
                logger.warning(f"未能自动打开 {self._target_chat_label()}，继续使用当前已打开的聊天窗口")
                return

            if self._wait_for_manual_target_chat_selection():
                return

            logger.warning(f"未能直接打开指定聊天: {self._target_chat_label()}")
            return

        self.target_chat_open_failures = 0
        latest_text = self._read_latest_chat_text()
        self.locked_chat_title = self._resolve_current_chat_title()
        self._load_chat_memory()
        if latest_text:
            self.last_seen_incoming_text = latest_text
            logger.info(f"已锁定聊天窗口，当前最新消息: {truncate_string(latest_text, 80)}")
        else:
            logger.info("已打开聊天窗口，但暂未读取到消息文本")
        self._update_runtime()

    def _handle_target_chat_step(self) -> str:
        """处理指定聊天的自动回复逻辑"""
        if not self.browser.is_page_alive():
            self.is_running = False
            return "浏览器页面已关闭，停止轮询"

        if not self.manual_target_chat_mode:
            if not self._open_target_chat():
                self.target_chat_open_failures += 1

                if self._can_use_current_chat_window():
                    self._lock_current_chat_window()
                    logger.warning(f"未自动定位到 {self._target_chat_label()}，切换为当前聊天窗口模式")
                elif (not self.manual_target_chat_prompted) and self._wait_for_manual_target_chat_selection():
                    return f"已手动锁定当前聊天窗口: {self._target_chat_label()}"
                elif self.target_chat_open_failures >= self.max_target_chat_open_failures:
                    self.is_running = False
                    return (
                        f"连续 {self.target_chat_open_failures} 次未找到指定聊天: "
                        f"{self._target_chat_label()}，已停止轮询"
                    )
                else:
                    return f"未找到指定聊天: {self._target_chat_label()}"
            else:
                self.target_chat_open_failures = 0

        latest_text = self._read_latest_chat_text()
        if not latest_text:
            self._update_runtime()
            return "未读取到聊天内容"

        if not self.last_seen_incoming_text:
            self.last_seen_incoming_text = latest_text
            self._update_runtime()
            return f"初始化最新消息: {truncate_string(latest_text, 80)}"

        if latest_text == self.last_sent_reply:
            self._update_runtime()
            return f"最新消息是机器人刚发送的回复: {truncate_string(latest_text, 80)}"

        if latest_text == self.last_seen_incoming_text:
            self._update_runtime()
            return f"暂无新消息: {truncate_string(latest_text, 80)}"

        history = self._read_recent_chat_history()
        self._maybe_refresh_chat_memory(history)
        reply = self._generate_target_chat_reply(latest_text, history)
        logger.info(f"💬 最新消息: {truncate_string(latest_text, 80)}")
        logger.info(f"🤖 自动回复: {truncate_string(reply, 80)}")

        if self._send_reply(reply):
            self.last_seen_incoming_text = latest_text
            self.last_sent_reply = reply
            self.runtime.note_message("assistant", reply, datetime.now().strftime("%Y-%m-%d %H:%M"))
            self._update_runtime()
            return f"已回复指定聊天: {self._target_chat_label()}"

        self.last_seen_incoming_text = latest_text
        self._update_runtime(error="回复发送失败")
        return "回复发送失败"

    def _open_target_chat(self) -> bool:
        """优先使用聊天项选择器打开指定聊天"""
        chat_item_selector = self.platform.config.selectors.get("chat_item", "")
        search_input_selector = self.platform.config.selectors.get("search_input", "")
        attempt_log: Dict[str, Any] = {
            "target_chat_name": self.target_chat_name,
            "chat_item_selector": chat_item_selector,
            "search_input_selector": search_input_selector,
            "chat_item_candidates": self.browser.find_text_candidates(
                self.target_chat_name,
                selector=chat_item_selector,
                limit=8,
            ) if chat_item_selector else [],
            "global_candidates": self.browser.find_text_candidates(
                self.target_chat_name,
                limit=8,
            ),
            "left_panel_candidates": self.browser.find_text_candidates(
                self.target_chat_name,
                limit=8,
                left_panel_only=True,
            ),
            "attempts": [],
        }

        logger.info(f"尝试打开指定聊天: {self.target_chat_name}")

        def record_attempt(strategy: str, success: bool) -> bool:
            browser_debug = self.browser.get_last_action_debug()
            attempt_log["attempts"].append({
                "strategy": strategy,
                "success": success,
                "browser_debug": browser_debug,
            })
            self.runtime.last_decision = truncate_string(
                f"打开聊天 {self.target_chat_name}: {strategy} -> {'success' if success else 'failed'}",
                180,
            )
            return success

        def finish(success: bool, matched_strategy: str = "") -> bool:
            attempt_log["success"] = success
            attempt_log["matched_strategy"] = matched_strategy
            status_text = "success" if success else "failed"
            strategy_text = matched_strategy or "all_strategies"
            self.runtime.last_decision = truncate_string(
                f"打开聊天 {self.target_chat_name}: {strategy_text} -> {status_text}",
                180,
            )
            self._trace("target_chat_open", attempt_log)
            self._update_runtime()
            return success

        if chat_item_selector:
            success = self.browser.click_selector_by_text(
                chat_item_selector,
                self.target_chat_name,
                wait=1,
                timeout_ms=2500
            )
            if record_attempt("click_selector_by_text", success):
                logger.info("通过聊天项选择器打开成功")
                return finish(True, "click_selector_by_text")

        success = self.browser.click_by_text(self.target_chat_name, wait=1, timeout_ms=2500)
        if record_attempt("click_by_text", success):
            logger.info("通过页面文本匹配打开成功")
            return finish(True, "click_by_text")

        if search_input_selector:
            logger.info("聊天项未命中，尝试通过搜索框定位聊天")
            success = self.browser.input_by_selector(
                search_input_selector,
                self.target_chat_name,
                wait=1,
                timeout_ms=2500
            )
            attempt_log["attempts"].append({
                "strategy": "input_by_selector",
                "success": success,
                "selector": search_input_selector,
                "browser_debug": self.browser.get_last_action_debug(),
            })
            if success:
                if chat_item_selector and self.browser.click_selector_by_text(
                    chat_item_selector,
                    self.target_chat_name,
                    wait=1,
                    timeout_ms=2500
                ):
                    record_attempt("search_then_click_selector_by_text", True)
                    logger.info("通过搜索结果聊天项打开成功")
                    return finish(True, "search_then_click_selector_by_text")
                elif chat_item_selector:
                    record_attempt("search_then_click_selector_by_text", False)

                if self.browser.click_by_text(self.target_chat_name, wait=1, timeout_ms=2500):
                    record_attempt("search_then_click_by_text", True)
                    logger.info("通过搜索结果文本匹配打开成功")
                    return finish(True, "search_then_click_by_text")
                record_attempt("search_then_click_by_text", False)

                if self.browser.click_visible_text_via_js(
                    self.target_chat_name,
                    wait=1,
                    left_panel_only=True,
                ) and self._can_use_current_chat_window():
                    record_attempt("search_then_click_visible_text_via_js", True)
                    logger.info("通过左侧搜索结果 JS 点击打开成功")
                    return finish(True, "search_then_click_visible_text_via_js")
                record_attempt("search_then_click_visible_text_via_js", False)

                keyboard_selected = False
                if self.browser.press_key("ArrowDown", wait=1):
                    keyboard_selected = self.browser.press_key("Enter", wait=1)
                attempt_log["attempts"].append({
                    "strategy": "search_then_keyboard_select",
                    "success": keyboard_selected and self._can_use_current_chat_window(),
                    "browser_debug": self.browser.get_last_action_debug(),
                })
                if keyboard_selected and self._can_use_current_chat_window():
                    logger.info("通过搜索结果键盘选择打开成功")
                    return finish(True, "search_then_keyboard_select")

                enter_opened = self.browser.press_key("Enter", wait=1) and self._can_use_current_chat_window()
                attempt_log["attempts"].append({
                    "strategy": "search_then_press_enter",
                    "success": enter_opened,
                    "browser_debug": self.browser.get_last_action_debug(),
                })
                if enter_opened:
                    logger.info("通过搜索框回车打开成功")
                    return finish(True, "search_then_press_enter")

        logger.warning(f"仍未找到指定聊天: {self.target_chat_name}")
        return finish(False)

    def _wait_for_manual_target_chat_selection(self) -> bool:
        """等待用户手动打开目标聊天窗口，再锁定当前聊天"""
        if self.manual_target_chat_prompted:
            return False

        self.manual_target_chat_prompted = True
        timeout_seconds = max(self.target_chat_prepare_timeout, 5)
        waited = 0
        check_interval = 3

        logger.warning(
            f"未能自动定位到 {self._target_chat_label()}，请在 {timeout_seconds} 秒内手动打开目标聊天窗口"
        )

        while waited < timeout_seconds:
            if not self.browser.is_page_alive():
                return False

            if self._can_use_current_chat_window():
                self.manual_target_chat_mode = True
                self.target_chat_open_failures = 0
                self.locked_chat_title = self._resolve_current_chat_title()
                self.last_locked_at = datetime.now().isoformat()
                self._load_chat_memory()
                latest_text = self._read_latest_chat_text()
                if latest_text:
                    self.last_seen_incoming_text = latest_text
                logger.info(f"已锁定当前手动打开的聊天窗口: {self._target_chat_label()}")
                self._update_runtime()
                return True

            time.sleep(check_interval)
            waited += check_interval
            if waited % 9 == 0:
                logger.info(f"等待手动打开目标聊天... ({waited}/{timeout_seconds}s)")

        logger.warning("等待手动打开目标聊天超时")
        return False

    def _lock_current_chat_window(self) -> None:
        """将当前页面视为已锁定聊天窗口"""
        self.manual_target_chat_mode = True
        self.target_chat_open_failures = 0
        self.locked_chat_title = self._resolve_current_chat_title()
        self.last_locked_at = datetime.now().isoformat()
        self._load_chat_memory()
        latest_text = self._read_latest_chat_text()
        if latest_text:
            self.last_seen_incoming_text = latest_text
            self.runtime.note_message("user", latest_text, datetime.now().strftime("%Y-%m-%d %H:%M"))
        self._update_runtime()

    def _read_recent_chat_history(self) -> List[Dict[str, str]]:
        """从 DOM 读取最近消息，压缩后提供给文本模型"""
        selector = self.platform.config.selectors.get("message_bubble", "")
        if not selector:
            return []

        items = self.browser.get_message_items(selector, limit=self.target_chat_dom_history_limit)
        history: List[Dict[str, str]] = []
        for item in items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            role = str(item.get("role", "unknown")).strip().lower() or "unknown"
            if role == "unknown" and self.last_sent_reply and text == self.last_sent_reply:
                role = "assistant"
            elif role == "unknown":
                role = "user"
            history.append({"role": role, "text": text})
        return history

    def _generate_target_chat_reply(self, latest_text: str, history: List[Dict[str, str]]) -> str:
        """优先使用轻量文本模型基于 DOM 历史生成回复"""
        if self.dom_chat_agent is None:
            return self.platform.generate_reply(latest_text)

        result = self.dom_chat_agent.generate_reply(
            latest_message=latest_text,
            history=history,
            target_label=self._chat_memory_label(),
            memory=self.chat_memory,
            fallback_reply=lambda: self.platform.generate_reply(latest_text),
        )
        if result.reason:
            logger.info(f"DOM 回复来源: {result.source} / {truncate_string(result.reason, 80)}")
        return result.message

    def _load_chat_memory(self) -> None:
        """加载当前锁定聊天的本地记忆"""
        label = self._chat_memory_label().strip()
        if not label:
            self.chat_memory = DOMChatMemory()
            return
        self.chat_memory = self.dom_chat_memory_store.load(label)
        if self.chat_memory.relationship_summary:
            logger.info(f"已加载聊天记忆: {truncate_string(self.chat_memory.relationship_summary, 80)}")
        self._update_runtime()

    def _maybe_refresh_chat_memory(self, history: List[Dict[str, str]]) -> None:
        """必要时刷新当前聊天的长期记忆"""
        if self.dom_chat_agent is None:
            return
        if not self.manual_target_chat_mode:
            return
        if len(history) < 4:
            return

        should_refresh = (
            not self.chat_memory.last_refreshed_at
            or len(history) >= self.chat_memory.source_message_count + 4
        )
        if not should_refresh:
            return

        self.chat_memory = self.dom_chat_agent.summarize_history(
            history=history,
            target_label=self._chat_memory_label(),
            existing_memory=self.chat_memory,
        )
        self.dom_chat_memory_store.save(self.chat_memory)
        if self.chat_memory.relationship_summary:
            logger.info(f"已刷新聊天记忆: {truncate_string(self.chat_memory.relationship_summary, 80)}")
        self._update_runtime()

    def _resolve_current_chat_title(self) -> str:
        """尽量从当前聊天窗口顶部识别真实聊天标题"""
        selector = self.platform.config.selectors.get("chat_header_title", "")
        candidates: List[str] = []
        if selector:
            text = self.browser.get_first_text_by_selector(selector)
            if text:
                candidates.append(text)

        candidates.extend([self.locked_chat_title, self.target_chat_name, "当前已锁定聊天"])
        ignored = {"telegram web", "messages", "chats", "all chats"}
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            if normalized.lower() in ignored:
                continue
            return normalized
        return "当前已锁定聊天"

    def _should_use_target_chat_flow(self) -> bool:
        """是否启用锁定聊天窗口模式"""
        if self.target_chat_name:
            return True
        return self.target_chat_mode in {"manual_lock", "current_window_only"}

    def _target_chat_label(self) -> str:
        """展示用聊天标签"""
        if self.locked_chat_title:
            return self.locked_chat_title
        if self.target_chat_name:
            return self.target_chat_name
        return "当前已锁定聊天"

    def _chat_memory_label(self) -> str:
        """记忆持久化使用的聊天标签"""
        if self.locked_chat_title:
            return self.locked_chat_title
        if self.target_chat_name:
            return self.target_chat_name
        return "当前已锁定聊天"

    def _can_use_current_chat_window(self) -> bool:
        """当前页面是否已经处于可聊天状态，可作为人工打开的目标聊天窗口使用"""
        message_input_selector = self.platform.config.selectors.get("message_input", "")
        message_bubble_selector = self.platform.config.selectors.get("message_bubble", "")

        has_input = bool(message_input_selector) and self.browser.has_visible_selector(message_input_selector)
        has_messages = bool(message_bubble_selector) and self.browser.has_visible_selector(message_bubble_selector)
        return has_input and has_messages

    def _read_latest_chat_text(self) -> str:
        """读取当前聊天窗口的最后一条可见消息"""
        selector = self.platform.config.selectors.get("message_bubble", "")
        if not selector:
            return ""

        texts = self.browser.get_texts_by_selector(selector)
        if not texts:
            return ""

        for text in reversed(texts):
            normalized = text.strip()
            if normalized:
                return normalized

        return ""

    def _apply_runtime_controls(self) -> bool:
        """同步后台控制状态，并处理 Web 模式下的控制命令"""
        automation_paused, proactive_paused, commands = self.control_store.pop_commands()
        self.runtime.automation_paused = automation_paused
        self.runtime.proactive_paused = proactive_paused

        for command in commands:
            if command.action == "clear_memory":
                self._clear_current_chat_memory()
                continue
            logger.warning(f"Web 模式暂不支持命令: {command.action}")

        self._update_runtime()
        return not automation_paused

    def _clear_current_chat_memory(self) -> None:
        """清空当前锁定聊天的本地记忆"""
        label = self._chat_memory_label().strip()
        cleared = self.dom_chat_memory_store.clear(label) if label else False
        self.chat_memory = DOMChatMemory(chat_label=label)
        if cleared:
            logger.info(f"已清空聊天记忆: {label}")
        else:
            logger.info(f"当前聊天没有可清空的历史记忆: {label or '未锁定聊天'}")
        self._update_runtime()

    def _update_runtime(self, status: Optional[str] = None, error: str = "") -> None:
        """刷新 Web 模式运行状态，供后台展示"""
        if status:
            self.runtime.status = status
        self.runtime.transport = "web"
        self.runtime.lock_mode = self.target_chat_mode
        self.runtime.target_chat = self.target_chat_name.strip() or self.locked_chat_title.strip()
        self.runtime.locked = bool(self.manual_target_chat_mode and self.locked_chat_title.strip())
        self.runtime.locked_chat_title = self.locked_chat_title.strip()
        self.runtime.last_locked_at = self.last_locked_at
        self.runtime.memory_summary = self.chat_memory.relationship_summary.strip()
        self.runtime.memory_file = str(self.dom_chat_memory_store.path_for_chat(self._chat_memory_label()))
        self.runtime.last_error = error
        self.runtime.debug_trace_file = str(getattr(self, "debug_trace_path", "") or "")
        self.runtime.last_updated_at = datetime.now().isoformat()
        self.runtime_store.save(self.runtime)

    def _send_reply(self, text: str) -> bool:
        """向当前聊天发送回复"""
        input_selector = self.platform.config.selectors.get("message_input", "")
        send_selector = self.platform.config.selectors.get("send_button", "")

        if not input_selector:
            logger.error("当前平台未配置 message_input 选择器")
            return False

        if not self.browser.input_by_selector(input_selector, text, wait=1):
            return False

        if send_selector and self.browser.click_by_selector(send_selector, wait=1):
            return True

        return self.browser.press_key("Enter", wait=1)

    def _build_visual_context(self) -> tuple[str, Dict[str, Any]]:
        """组合给视觉模型的 DOM 过滤摘要，同时保留结构化调试信息"""
        state = self.browser.get_state()
        clickable = state.get_clickable_elements()
        inputs = state.get_input_elements()
        elements = []
        for element in state.elements[:20]:
            elements.append({
                "index": element.index,
                "tag": element.tag,
                "text": element.text,
                "clickable": element.clickable,
                "input_field": element.input_field,
                "selector": element.selector,
                "selector_index": getattr(element, "selector_index", 0),
            })

        lines = [
            f"页面 URL: {state.url or '-'}",
            f"页面标题: {state.title or '-'}",
            f"DOM 统计: 共 {len(state.elements)} 个候选元素，可点击 {len(clickable)} 个，输入框 {len(inputs)} 个",
            "前 20 个候选元素:",
        ]
        if elements:
            for item in elements:
                marker = []
                if item["clickable"]:
                    marker.append("clickable")
                if item["input_field"]:
                    marker.append("input")
                marker_text = ",".join(marker) or "plain"
                lines.append(
                    f"- #{item['index']} [{marker_text}] {item['tag']} text={item['text']!r} "
                    f"selector={item['selector']}[{item['selector_index']}]"
                )
        else:
            lines.append("- 无可读 DOM 候选元素")

        payload = {
            "url": state.url,
            "title": state.title,
            "element_count": len(state.elements),
            "clickable_count": len(clickable),
            "input_count": len(inputs),
            "elements": elements,
        }
        return "\n".join(lines), payload

    def _trace(self, stage: str, payload: Dict[str, Any]) -> None:
        """写入结构化调试轨迹，便于定位每一轮卡在哪个节点"""
        trace_path = getattr(self, "debug_trace_path", None)
        if not trace_path:
            return

        trace_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now().isoformat(),
            "step": self.step,
            "stage": stage,
            "payload": payload,
        }
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.runtime.last_step_trace = truncate_string(
            f"{stage}: {json.dumps(payload, ensure_ascii=False)}",
            240,
        )
