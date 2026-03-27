#!/usr/bin/env python3
"""
自由网页操控机器人
可以操控任意网页，根据用户目标自动执行操作
支持录制模式，将操作流程固化为工作流
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .browser_controller import BrowserController
from .runtime_control import RuntimeDashboardStore, RuntimeDashboard, PendingDraft
from .utils.logger import logger
from .utils.helpers import truncate_string
from .vision_agent import KimiVisionAgent, ActionDecision
from .workflow_engine import WorkflowRecorder, WorkflowPlayer, WorkflowManager


# 默认保存截图的目录
SCREENSHOT_DIR = Path("./screenshots")


class FreeWebBot:
    """自由网页操控机器人"""

    def __init__(
        self,
        url: str,
        goal: str,
        max_steps: int = 50,
        step_delay: int = 3,
        headless: Optional[bool] = None,
        record_mode: bool = False,      # 录制模式
        workflow_name: Optional[str] = None,  # 工作流名称（录制时用）
        workflow_file: Optional[str] = None,  # 工作流文件（回放时用）
        workflow_params: Optional[Dict[str, Any]] = None,  # 工作流参数
    ):
        self.url = url
        self.goal = goal
        self.max_steps = max_steps
        self.step_delay = step_delay
        self.headless = headless
        self.record_mode = record_mode
        self.workflow_file = workflow_file
        self.workflow_params = workflow_params or {}

        self.step = 0
        self.is_running = False
        self.session_dir = SCREENSHOT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir.mkdir(exist_ok=True)
        self.debug_trace_path = self.session_dir / "debug_trace.jsonl"

        self.browser = BrowserController(headless=headless)
        self.vision = KimiVisionAgent()
        self.runtime_store = RuntimeDashboardStore(self.session_dir / "runtime.json")
        self.runtime = RuntimeDashboard(
            session_name="free_web",
            target_chat=self.url,
        )
        self.runtime.debug_trace_file = str(self.debug_trace_path)
        
        # 录制相关
        self.recorder: Optional[WorkflowRecorder] = None
        self.player: Optional[WorkflowPlayer] = None
        
        if record_mode:
            # 录制模式：创建录制器
            wf_name = workflow_name or f"recorded_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.recorder = WorkflowRecorder(
                workflow_name=wf_name,
                description=f"录制的任务: {goal}",
                start_url=url,
            )
            self.recorder.set_session_dir(self.session_dir)
            self.recorder.add_parameter("search_query", "string", "", "搜索关键词")
            logger.info(f"🎬 录制模式已启用，工作流将保存为: {wf_name}")
            
        elif workflow_file:
            # 回放模式：加载工作流
            self._load_workflow_player()

    def _load_workflow_player(self) -> bool:
        """加载工作流播放器"""
        try:
            manager = WorkflowManager()
            workflow = manager.load_workflow(self.workflow_file)
            
            if not workflow:
                logger.error(f"工作流未找到: {self.workflow_file}")
                return False
            
            self.player = WorkflowPlayer(
                workflow=workflow,
                browser=self.browser,
                parameters=self.workflow_params,
            )
            logger.info(f"📋 已加载工作流: {workflow.name} ({len(workflow.steps)} 步骤)")
            return True
            
        except Exception as e:
            logger.error(f"加载工作流失败: {e}")
            return False

    def start(self) -> None:
        """启动机器人"""
        logger.info("=" * 60)
        logger.info(f"🌐 自由网页操控启动")
        logger.info(f"目标 URL: {self.url}")
        logger.info(f"任务目标: {self.goal}")
        logger.info("=" * 60)

        # 回放模式：直接执行工作流
        if self.player:
            self._playback_mode()
            return

        # 设置系统提示词
        self.vision.set_system_prompt(self._build_system_prompt())

        # 打开浏览器
        logger.info(f"正在打开网页: {self.url}")
        if not self.browser.open(self.url, wait=5):
            logger.error("打开网页失败")
            return

        self.is_running = True
        self._update_runtime()

        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("用户中断运行")
        finally:
            self.stop()
    
    def _playback_mode(self) -> None:
        """回放模式：执行预录工作流"""
        if not self.player:
            logger.error("播放器未初始化")
            return
        
        self.is_running = True
        results = self.player.run()
        
        # 导出报告
        report_path = self.session_dir / "workflow_report.json"
        self.player.export_report(str(report_path))
        
        # 关闭浏览器
        self.browser.close()
        
        # 统计
        success_count = sum(1 for r in results if r["success"])
        logger.info(f"\n工作流执行完成: {success_count}/{len(results)} 步骤成功")

    def stop(self) -> None:
        """停止机器人"""
        self.is_running = False
        
        # 录制模式：保存工作流
        if self.recorder and len(self.recorder.workflow.steps) > 0:
            try:
                workflow = self.recorder.finalize()
                manager = WorkflowManager()
                filepath = manager.save_workflow(workflow)
                logger.info(f"💾 工作流已保存: {filepath}")
                logger.info(f"   步骤数: {len(workflow.steps)}")
                logger.info(f"   使用回放模式: python run.py -> 选择工作流")
            except Exception as e:
                logger.error(f"保存工作流失败: {e}")
        
        self.browser.close()
        self.runtime.is_running = False
        self.runtime.last_updated_at = datetime.now().isoformat()
        self.runtime_store.save(self.runtime)
        logger.info("机器人已停止")

    def _main_loop(self) -> None:
        """主循环"""
        while self.is_running and self.step < self.max_steps:
            self.step += 1
            self.runtime.current_step = self.step
            self.runtime.last_updated_at = datetime.now().isoformat()

            logger.info(f"\n{'='*50}")
            logger.info(f"[步骤 {self.step}/{self.max_steps}]")

            # 1. 截图
            screenshot_path = self.browser.screenshot(str(self.session_dir / f"step_{self.step:03d}.png"))
            if not screenshot_path:
                logger.error("截图失败，停止运行")
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

            logger.info(f"🧠 AI 决策: {truncate_string(decision.reason, 60)}")
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

            # 4. 检查是否完成
            if decision.action == "done":
                logger.info("[任务完成]")
                self.runtime.status = "completed"
                break

            # 5. 等待
            wait_seconds = decision.params.get("seconds", self.step_delay)
            if decision.action != "wait":
                wait_seconds = self.step_delay

            self.runtime.status = "running"
            self._update_runtime()
            time.sleep(wait_seconds)

        if self.step >= self.max_steps:
            logger.info("达到最大步数，自动停止")
            self.runtime.status = "max_steps_reached"

        self.runtime.is_running = False
        self.runtime.last_updated_at = datetime.now().isoformat()
        self.runtime_store.save(self.runtime)

    def _execute_decision(self, decision: ActionDecision) -> str:
        """执行决策"""
        action = decision.action
        params = decision.params

        handlers = {
            "open": lambda: self.browser.open(params.get("url", self.url)),
            "click": lambda: self.browser.click(params.get("index", 1)),
            "click_by_text": lambda: self.browser.click_by_text(params.get("text", "")),
            "click_by_selector": lambda: self.browser.click_by_selector(params.get("selector", "")),
            "type": lambda: self.browser.type_text(params.get("text", "")),
            "input": lambda: self.browser.input_to_element(params.get("index", 1), params.get("text", "")),
            "input_by_selector": lambda: self.browser.input_by_selector(params.get("selector", ""), params.get("text", "")),
            "press_key": lambda: self.browser.press_key(params.get("key", "Enter")),
            "scroll": lambda: self._handle_scroll(params),
            "back": lambda: self.browser.press_key("Alt+Left"),
            "wait": lambda: self._handle_wait(params),
            "done": lambda: "任务完成",
            "state": lambda: str(len(self.browser.get_state().elements)),
        }

        handler = handlers.get(action)
        if handler:
            try:
                # 录制模式：记录步骤
                if self.recorder and action != "state":
                    self.recorder.record_step(
                        step_type=action,
                        params=params,
                        description=decision.reason,
                        browser=self.browser,
                        snapshot=True,
                    )
                
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

    def _handle_scroll(self, params: Dict[str, Any]) -> str:
        """处理滚动"""
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)

        page = self.browser.get_page()
        if not page:
            return "浏览器未打开"

        if direction == "down":
            page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "bottom":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "top":
            page.evaluate("window.scrollTo(0, 0)")

        time.sleep(1)
        return f"滚动 {direction}"

    def _handle_wait(self, params: Dict[str, Any]) -> str:
        """处理等待"""
        seconds = params.get("seconds", 3)
        time.sleep(seconds)
        return f"等待 {seconds} 秒"

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return f"""你是一个智能网页操控助手。你的任务是分析网页截图，并决定如何操作浏览器来完成用户指定的目标。

## 用户目标
{self.goal}

## 可用操作
1. `open` - 打开网页，params: {{"url": "..."}}
2. `click` - 点击指定索引的元素，params: {{"index": 数字}}
3. `click_by_text` - 点击包含指定文本的元素，params: {{"text": "..."}}
4. `click_by_selector` - 点击 CSS 选择器匹配的元素，params: {{"selector": "..."}}
5. `type` - 在当前焦点输入文本，params: {{"text": "..."}}
6. `input` - 点击元素并输入文本，params: {{"index": 数字, "text": "..."}}
7. `input_by_selector` - 通过选择器输入文本，params: {{"selector": "...", "text": "..."}}
8. `press_key` - 按下键盘按键，params: {{"key": "Enter/Escape/Tab/..."}}
9. `scroll` - 滚动页面，params: {{"direction": "down/up/bottom/top", "amount": 500}}
10. `back` - 返回上一页，params: {{}}
11. `wait` - 等待页面响应，params: {{"seconds": 3}}
12. `state` - 获取页面元素列表，params: {{}}
13. `done` - 任务完成，params: {{}}

## 工作流程
1. 分析当前页面截图，理解页面结构和当前状态
2. 根据用户目标决定下一步操作
3. 如果页面加载中，请先等待
4. 如果需要填写表单，先点击输入框再输入
5. 操作后等待页面响应
6. 任务完成时返回 done 操作

## 重要提示
- 每次只返回一个操作
- 优先使用 `click_by_text` 点击可见文本，更可靠
- 如果找不到元素，尝试滚动页面
- 表单填写：先点击输入框聚焦，再输入内容
- 操作后等待 2-3 秒让页面响应
- 如果遇到验证码或需要登录，可以等待用户处理

## 返回格式
必须返回 JSON 格式：
```json
{{
  "action": "操作类型",
  "params": {{具体参数}},
  "reason": "决策原因",
  "confidence": 0.95
}}
```
"""

    def _build_visual_context(self) -> tuple[str, Dict[str, Any]]:
        """构建视觉上下文"""
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
            f"任务目标: {self.goal}",
            f"当前步骤: {self.step}/{self.max_steps}",
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
                    f"- #{item['index']} [{marker_text}] {item['tag']} text={item['text']!r}"
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
        """记录调试轨迹"""
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

    def _update_runtime(self) -> None:
        """更新运行时状态"""
        self.runtime.is_running = self.is_running
        self.runtime.current_step = self.step
        self.runtime.session_dir = str(self.session_dir)
        self.runtime.debug_trace_file = str(getattr(self, "debug_trace_path", "") or "")
        self.runtime_store.save(self.runtime)
