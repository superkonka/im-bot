#!/usr/bin/env python3
"""
IM 机器人主类
整合浏览器控制、视觉分析和平台适配
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .browser_controller import BrowserController
from .vision_agent import KimiVisionAgent, ActionDecision
from .platforms import get_platform, BasePlatform
from .utils.logger import logger
from .utils.helpers import truncate_string
from .config import (
    SCREENSHOT_DIR, DEFAULT_MAX_STEPS, DEFAULT_STEP_DELAY, get_app_config
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
        self.last_seen_incoming_text = ""
        self.last_sent_reply = ""
        self.target_chat_open_failures = 0
        self.max_target_chat_open_failures = 3
        self.manual_target_chat_mode = False
        
        # 组件
        self.browser = BrowserController(headless=headless)
        self.vision = KimiVisionAgent()
        
        # 设置系统提示词
        self.vision.set_system_prompt(self.platform.get_system_prompt())
        
        # 状态
        self.step = 0
        self.is_running = False
        self.session_dir = SCREENSHOT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir.mkdir(exist_ok=True)
        
    def start(self) -> None:
        """启动机器人"""
        logger.banner(f"启动 {self.platform.config.name} 机器人")
        
        # 显示配置信息
        logger.info(f"目标网址: {self.platform.config.url}")
        logger.info(f"登录方式: {self.platform.config.login_method}")
        logger.info(f"最大步数: {self.max_steps}")
        logger.info(f"步进延迟: {self.step_delay}s")
        
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

            if self.target_chat_name:
                self._prepare_target_chat()
            
            # 主循环
            self._main_loop()
            
        except KeyboardInterrupt:
            logger.warning("用户中断")
        except Exception as e:
            logger.error(f"运行错误: {e}")
        finally:
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
            
            if self.target_chat_name:
                result = self._handle_target_chat_step()
                logger.info(f"✅ 结果: {truncate_string(str(result), 80)}")
                time.sleep(self.step_delay)
                continue

            # 1. 截图
            screenshot_path = self._take_screenshot(f"step_{self.step:03d}")
            if not screenshot_path:
                logger.error("截图失败，停止主循环")
                break

            # 2. 决策
            decision = self.vision.analyze_screenshot(screenshot_path)
            
            logger.info(f"🧠 决策: {truncate_string(decision.reason, 60)}")
            logger.info(f"🎯 操作: {decision.action} {decision.params}")
            
            # 3. 执行
            result = self._execute_decision(decision)
            logger.info(f"✅ 结果: {truncate_string(str(result), 80)}")
            
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
                return str(handler())
            except Exception as e:
                logger.error(f"执行操作失败: {e}")
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
        logger.info(f"指定聊天模式已启用: {self.target_chat_name}")
        if not self._open_target_chat():
            if self._can_use_current_chat_window():
                self.manual_target_chat_mode = True
                logger.warning(f"未能自动打开 {self.target_chat_name}，继续使用当前已打开的聊天窗口")
                return

            logger.warning(f"未能直接打开指定聊天: {self.target_chat_name}")
            return

        self.target_chat_open_failures = 0
        latest_text = self._read_latest_chat_text()
        if latest_text:
            self.last_seen_incoming_text = latest_text
            logger.info(f"已锁定聊天窗口，当前最新消息: {truncate_string(latest_text, 80)}")
        else:
            logger.info("已打开聊天窗口，但暂未读取到消息文本")

    def _handle_target_chat_step(self) -> str:
        """处理指定聊天的自动回复逻辑"""
        if not self.browser.is_page_alive():
            self.is_running = False
            return "浏览器页面已关闭，停止轮询"

        if not self.manual_target_chat_mode:
            if not self._open_target_chat():
                self.target_chat_open_failures += 1

                if self._can_use_current_chat_window():
                    self.manual_target_chat_mode = True
                    logger.warning(f"未自动定位到 {self.target_chat_name}，切换为当前聊天窗口模式")
                elif self.target_chat_open_failures >= self.max_target_chat_open_failures:
                    self.is_running = False
                    return (
                        f"连续 {self.target_chat_open_failures} 次未找到指定聊天: "
                        f"{self.target_chat_name}，已停止轮询"
                    )
                else:
                    return f"未找到指定聊天: {self.target_chat_name}"
            else:
                self.target_chat_open_failures = 0

        latest_text = self._read_latest_chat_text()
        if not latest_text:
            return "未读取到聊天内容"

        if not self.last_seen_incoming_text:
            self.last_seen_incoming_text = latest_text
            return f"初始化最新消息: {truncate_string(latest_text, 80)}"

        if latest_text == self.last_sent_reply:
            return f"最新消息是机器人刚发送的回复: {truncate_string(latest_text, 80)}"

        if latest_text == self.last_seen_incoming_text:
            return f"暂无新消息: {truncate_string(latest_text, 80)}"

        reply = self.platform.generate_reply(latest_text)
        logger.info(f"💬 最新消息: {truncate_string(latest_text, 80)}")
        logger.info(f"🤖 自动回复: {truncate_string(reply, 80)}")

        if self._send_reply(reply):
            self.last_seen_incoming_text = latest_text
            self.last_sent_reply = reply
            return f"已回复指定聊天: {self.target_chat_name}"

        self.last_seen_incoming_text = latest_text
        return "回复发送失败"

    def _open_target_chat(self) -> bool:
        """优先使用聊天项选择器打开指定聊天"""
        chat_item_selector = self.platform.config.selectors.get("chat_item", "")
        search_input_selector = self.platform.config.selectors.get("search_input", "")

        logger.info(f"尝试打开指定聊天: {self.target_chat_name}")

        if chat_item_selector and self.browser.click_selector_by_text(
            chat_item_selector,
            self.target_chat_name,
            wait=1,
            timeout_ms=2500
        ):
            logger.info("通过聊天项选择器打开成功")
            return True

        if self.browser.click_by_text(self.target_chat_name, wait=1, timeout_ms=2500):
            logger.info("通过页面文本匹配打开成功")
            return True

        if search_input_selector:
            logger.info("聊天项未命中，尝试通过搜索框定位聊天")
            if self.browser.input_by_selector(
                search_input_selector,
                self.target_chat_name,
                wait=1,
                timeout_ms=2500
            ):
                if chat_item_selector and self.browser.click_selector_by_text(
                    chat_item_selector,
                    self.target_chat_name,
                    wait=1,
                    timeout_ms=2500
                ):
                    logger.info("通过搜索结果聊天项打开成功")
                    return True

                if self.browser.click_by_text(self.target_chat_name, wait=1, timeout_ms=2500):
                    logger.info("通过搜索结果文本匹配打开成功")
                    return True

        logger.warning(f"仍未找到指定聊天: {self.target_chat_name}")
        return False

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
