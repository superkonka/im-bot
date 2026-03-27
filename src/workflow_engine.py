#!/usr/bin/env python3
"""
工作流引擎 - 录制和回放网页操作流程
"""
import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

from .browser_controller import BrowserController
from .utils.logger import logger
from .utils.helpers import truncate_string


class StepType(Enum):
    """步骤类型"""
    OPEN = "open"                    # 打开网页
    CLICK = "click"                  # 点击索引
    CLICK_BY_TEXT = "click_by_text"  # 点击文本
    CLICK_BY_SELECTOR = "click_by_selector"  # 点击选择器
    INPUT = "input"                  # 输入到索引
    INPUT_BY_SELECTOR = "input_by_selector"  # 输入到选择器
    TYPE = "type"                    # 直接输入
    PRESS_KEY = "press_key"          # 按键
    SCROLL = "scroll"                # 滚动
    BACK = "back"                    # 返回
    WAIT = "wait"                    # 等待
    WAIT_FOR_ELEMENT = "wait_for_element"  # 等待元素出现
    SNAPSHOT = "snapshot"            # 截图验证
    DONE = "done"                    # 完成


@dataclass
class WorkflowStep:
    """工作流步骤"""
    step_number: int
    step_type: str
    params: Dict[str, Any]
    description: str = ""           # 步骤说明
    snapshot_path: str = ""         # 截图路径（录制时）
    dom_state: Dict[str, Any] = field(default_factory=dict)  # DOM 状态
    validation: Dict[str, Any] = field(default_factory=dict)  # 验证规则
    retry_count: int = 3            # 重试次数
    retry_delay: float = 1.0        # 重试间隔
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "step_type": self.step_type,
            "params": self.params,
            "description": self.description,
            "snapshot_path": self.snapshot_path,
            "dom_state": self.dom_state,
            "validation": self.validation,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_number=data.get("step_number", 0),
            step_type=data.get("step_type", ""),
            params=data.get("params", {}),
            description=data.get("description", ""),
            snapshot_path=data.get("snapshot_path", ""),
            dom_state=data.get("dom_state", {}),
            validation=data.get("validation", {}),
            retry_count=data.get("retry_count", 3),
            retry_delay=data.get("retry_delay", 1.0),
        )


@dataclass
class Workflow:
    """工作流定义"""
    name: str                       # 工作流名称
    description: str                # 工作流描述
    start_url: str                  # 起始 URL
    parameters: List[Dict[str, Any]] = field(default_factory=list)  # 参数定义
    steps: List[WorkflowStep] = field(default_factory=list)  # 步骤列表
    created_at: str = ""           # 创建时间
    updated_at: str = ""           # 更新时间
    version: str = "1.0"           # 版本
    author: str = ""               # 作者
    tags: List[str] = field(default_factory=list)  # 标签
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "start_url": self.start_url,
            "parameters": self.parameters,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        workflow = cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            start_url=data.get("start_url", ""),
            parameters=data.get("parameters", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            version=data.get("version", "1.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )
        workflow.steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        return workflow
    
    def save(self, filepath: str) -> None:
        """保存工作流到文件"""
        self.updated_at = datetime.now().isoformat()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"工作流已保存: {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> "Workflow":
        """从文件加载工作流"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


class WorkflowRecorder:
    """工作流录制器 - 在 AI 执行时记录操作"""
    
    def __init__(self, workflow_name: str, description: str = "", start_url: str = ""):
        self.workflow = Workflow(
            name=workflow_name,
            description=description,
            start_url=start_url,
        )
        self.current_step = 0
        self.session_dir: Optional[Path] = None
        
    def set_session_dir(self, session_dir: Path) -> None:
        """设置会话目录，用于保存截图"""
        self.session_dir = session_dir
        
    def record_step(
        self,
        step_type: str,
        params: Dict[str, Any],
        description: str = "",
        browser: Optional[BrowserController] = None,
        snapshot: bool = True,
    ) -> WorkflowStep:
        """记录一个步骤"""
        self.current_step += 1
        
        # 获取 DOM 状态
        dom_state = {}
        if browser:
            try:
                state = browser.get_state()
                dom_state = {
                    "url": state.url,
                    "title": state.title,
                    "element_count": len(state.elements),
                    "clickable_count": len(state.get_clickable_elements()),
                    "input_count": len(state.get_input_elements()),
                }
            except Exception as e:
                logger.warning(f"获取 DOM 状态失败: {e}")
        
        # 截图
        snapshot_path = ""
        if snapshot and browser and self.session_dir:
            try:
                filename = f"workflow_step_{self.current_step:03d}.png"
                snapshot_path = str(self.session_dir / filename)
                browser.screenshot(snapshot_path)
            except Exception as e:
                logger.warning(f"截图失败: {e}")
        
        step = WorkflowStep(
            step_number=self.current_step,
            step_type=step_type,
            params=params,
            description=description,
            snapshot_path=snapshot_path,
            dom_state=dom_state,
        )
        
        self.workflow.steps.append(step)
        logger.info(f"[录制] 步骤 {self.current_step}: {step_type} - {description}")
        
        return step
    
    def add_parameter(
        self,
        name: str,
        param_type: str = "string",
        default: Any = None,
        description: str = "",
        required: bool = True,
    ) -> None:
        """添加参数定义"""
        self.workflow.parameters.append({
            "name": name,
            "type": param_type,
            "default": default,
            "description": description,
            "required": required,
        })
    
    def finalize(self) -> Workflow:
        """完成录制，返回工作流"""
        logger.info(f"[录制完成] 共 {len(self.workflow.steps)} 个步骤")
        return self.workflow


class WorkflowPlayer:
    """工作流播放器 - 按记录的操作执行"""
    
    def __init__(
        self,
        workflow: Workflow,
        browser: Optional[BrowserController] = None,
        parameters: Optional[Dict[str, Any]] = None,
        headless: Optional[bool] = None,
    ):
        self.workflow = workflow
        self.parameters = parameters or {}
        self.browser = browser or BrowserController(headless=headless)
        self.current_step = 0
        self.results: List[Dict[str, Any]] = []
        self.is_running = False
        
    def _resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """解析参数，替换变量引用"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                # 替换 ${param_name} 格式的变量
                resolved[key] = self._replace_variables(value)
            else:
                resolved[key] = value
        return resolved
    
    def _replace_variables(self, text: str) -> str:
        """替换文本中的变量"""
        pattern = r'\$\{(\w+)\}'
        
        def replace_match(match):
            var_name = match.group(1)
            if var_name in self.parameters:
                return str(self.parameters[var_name])
            # 查找工作流参数默认值
            for param in self.workflow.parameters:
                if param["name"] == var_name and param.get("default") is not None:
                    return str(param["default"])
            return match.group(0)  # 保留原样
        
        return re.sub(pattern, replace_match, text)
    
    def _validate_step(self, step: WorkflowStep) -> tuple[bool, str]:
        """验证步骤是否成功执行"""
        validation = step.validation
        if not validation:
            return True, ""
        
        # URL 验证
        if "url_contains" in validation:
            current_url = self.browser._page.url if self.browser._page else ""
            expected = validation["url_contains"]
            if expected not in current_url:
                return False, f"URL 验证失败: 期望包含 '{expected}'，实际 '{current_url}'"
        
        # 元素存在验证
        if "element_exists" in validation:
            selector = validation["element_exists"]
            if not self.browser.has_visible_selector(selector):
                return False, f"元素验证失败: 未找到 '{selector}'"
        
        # 文本存在验证
        if "text_exists" in validation:
            text = validation["text_exists"]
            candidates = self.browser.find_text_candidates(text, limit=1)
            if not candidates:
                return False, f"文本验证失败: 未找到 '{text}'"
        
        return True, ""
    
    def execute_step(self, step: WorkflowStep) -> Dict[str, Any]:
        """执行单个步骤"""
        result = {
            "step_number": step.step_number,
            "step_type": step.step_type,
            "success": False,
            "message": "",
            "retry_count": 0,
        }
        
        # 解析参数
        params = self._resolve_params(step.params)
        
        # 执行操作（带重试）
        for attempt in range(step.retry_count):
            try:
                success = self._execute_operation(step.step_type, params)
                if success:
                    # 验证
                    valid, msg = self._validate_step(step)
                    if valid:
                        result["success"] = True
                        result["message"] = f"成功: {step.description}"
                        break
                    else:
                        result["message"] = f"验证失败: {msg}"
                        if attempt < step.retry_count - 1:
                            time.sleep(step.retry_delay)
                else:
                    result["message"] = f"操作执行失败"
                    if attempt < step.retry_count - 1:
                        time.sleep(step.retry_delay)
                
                result["retry_count"] = attempt + 1
                
            except Exception as e:
                result["message"] = f"异常: {e}"
                if attempt < step.retry_count - 1:
                    time.sleep(step.retry_delay)
        
        return result
    
    def _execute_operation(self, step_type: str, params: Dict[str, Any]) -> bool:
        """执行具体操作"""
        handlers: Dict[str, Callable] = {
            StepType.OPEN.value: lambda: self.browser.open(params.get("url", "")),
            StepType.CLICK.value: lambda: self.browser.click(params.get("index", 1)),
            StepType.CLICK_BY_TEXT.value: lambda: self.browser.click_by_text(params.get("text", "")),
            StepType.CLICK_BY_SELECTOR.value: lambda: self.browser.click_by_selector(params.get("selector", "")),
            StepType.INPUT.value: lambda: self.browser.input_to_element(params.get("index", 1), params.get("text", "")),
            StepType.INPUT_BY_SELECTOR.value: lambda: self.browser.input_by_selector(params.get("selector", ""), params.get("text", "")),
            StepType.TYPE.value: lambda: self.browser.type_text(params.get("text", "")),
            StepType.PRESS_KEY.value: lambda: self.browser.press_key(params.get("key", "Enter")),
            StepType.BACK.value: lambda: self.browser.press_key("Alt+Left"),
            StepType.WAIT.value: lambda: self._handle_wait(params),
            StepType.SCROLL.value: lambda: self._handle_scroll(params),
            StepType.DONE.value: lambda: True,
        }
        
        handler = handlers.get(step_type)
        if not handler:
            logger.warning(f"未知的步骤类型: {step_type}")
            return False
        
        try:
            return bool(handler())
        except Exception as e:
            logger.error(f"执行 {step_type} 失败: {e}")
            return False
    
    def _handle_wait(self, params: Dict[str, Any]) -> bool:
        """处理等待"""
        seconds = params.get("seconds", 1)
        time.sleep(seconds)
        return True
    
    def _handle_scroll(self, params: Dict[str, Any]) -> bool:
        """处理滚动"""
        page = self.browser.get_page()
        if not page:
            return False
        
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)
        
        if direction == "down":
            page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "bottom":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "top":
            page.evaluate("window.scrollTo(0, 0)")
        
        return True
    
    def run(self) -> List[Dict[str, Any]]:
        """运行整个工作流"""
        logger.info("=" * 60)
        logger.info(f"▶️  开始执行工作流: {self.workflow.name}")
        logger.info(f"描述: {self.workflow.description}")
        logger.info(f"步骤数: {len(self.workflow.steps)}")
        logger.info("=" * 60)
        
        self.is_running = True
        self.results = []
        
        # 如果没有浏览器会话，先打开起始 URL
        if not self.browser.is_open and self.workflow.start_url:
            logger.info(f"打开起始 URL: {self.workflow.start_url}")
            self.browser.open(self.workflow.start_url, wait=3)
        
        for step in self.workflow.steps:
            if not self.is_running:
                logger.info("工作流被中断")
                break
            
            self.current_step = step.step_number
            logger.info(f"\n[步骤 {step.step_number}/{len(self.workflow.steps)}] {step.step_type}")
            logger.info(f"说明: {step.description}")
            
            result = self.execute_step(step)
            self.results.append(result)
            
            if result["success"]:
                logger.info(f"✅ {result['message']}")
            else:
                logger.error(f"❌ {result['message']}")
                # 可以选择中断或继续
                # break
        
        # 统计结果
        success_count = sum(1 for r in self.results if r["success"])
        logger.info("\n" + "=" * 60)
        logger.info(f"工作流执行完成: {success_count}/{len(self.results)} 成功")
        logger.info("=" * 60)
        
        self.is_running = False
        return self.results
    
    def stop(self) -> None:
        """停止工作流"""
        self.is_running = False
    
    def export_report(self, filepath: str) -> None:
        """导出执行报告"""
        report = {
            "workflow_name": self.workflow.name,
            "execution_time": datetime.now().isoformat(),
            "parameters": self.parameters,
            "results": self.results,
            "summary": {
                "total": len(self.results),
                "success": sum(1 for r in self.results if r["success"]),
                "failed": sum(1 for r in self.results if not r["success"]),
            }
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"执行报告已保存: {filepath}")


class WorkflowManager:
    """工作流管理器 - 管理工作流的 CRUD"""
    
    WORKFLOW_DIR = Path("./workflows")
    
    def __init__(self):
        self.WORKFLOW_DIR.mkdir(exist_ok=True)
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有工作流"""
        workflows = []
        for file_path in self.WORKFLOW_DIR.glob("*.json"):
            try:
                wf = Workflow.load(str(file_path))
                workflows.append({
                    "filename": file_path.name,
                    "name": wf.name,
                    "description": wf.description,
                    "step_count": len(wf.steps),
                    "updated_at": wf.updated_at,
                })
            except Exception as e:
                logger.warning(f"加载工作流失败 {file_path}: {e}")
        
        return sorted(workflows, key=lambda x: x["updated_at"], reverse=True)
    
    def get_workflow_path(self, name: str) -> Path:
        """获取工作流文件路径"""
        # 清理文件名
        safe_name = re.sub(r'[^\w\-_.]', '_', name)
        return self.WORKFLOW_DIR / f"{safe_name}.json"
    
    def save_workflow(self, workflow: Workflow, custom_name: Optional[str] = None) -> str:
        """保存工作流"""
        name = custom_name or workflow.name
        filepath = self.get_workflow_path(name)
        workflow.save(str(filepath))
        return str(filepath)
    
    def load_workflow(self, name: str) -> Optional[Workflow]:
        """加载工作流"""
        filepath = self.get_workflow_path(name)
        if not filepath.exists():
            # 尝试直接作为文件名
            filepath = self.WORKFLOW_DIR / name
            if not filepath.exists():
                return None
        
        return Workflow.load(str(filepath))
    
    def delete_workflow(self, name: str) -> bool:
        """删除工作流"""
        filepath = self.get_workflow_path(name)
        if filepath.exists():
            filepath.unlink()
            logger.info(f"工作流已删除: {filepath}")
            return True
        return False
