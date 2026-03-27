#!/usr/bin/env python3
"""
工作流引擎测试
"""
import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workflow_engine import (
    Workflow, WorkflowStep, WorkflowRecorder, WorkflowPlayer, 
    WorkflowManager, StepType
)


class TestWorkflow(unittest.TestCase):
    """工作流基础测试"""

    def test_workflow_creation(self):
        """测试创建工作流"""
        wf = Workflow(
            name="测试工作流",
            description="用于测试的工作流",
            start_url="https://example.com",
        )
        
        self.assertEqual(wf.name, "测试工作流")
        self.assertEqual(wf.description, "用于测试的工作流")
        self.assertEqual(wf.start_url, "https://example.com")
        self.assertEqual(len(wf.steps), 0)
        self.assertIsNotNone(wf.created_at)
        
    def test_workflow_serialization(self):
        """测试工作流序列化"""
        wf = Workflow(
            name="测试",
            description="测试描述",
            start_url="https://test.com",
        )
        wf.steps.append(WorkflowStep(
            step_number=1,
            step_type="click",
            params={"index": 1},
            description="点击按钮",
        ))
        
        data = wf.to_dict()
        self.assertEqual(data["name"], "测试")
        self.assertEqual(len(data["steps"]), 1)
        self.assertEqual(data["steps"][0]["step_type"], "click")
        
    def test_workflow_save_and_load(self):
        """测试保存和加载工作流"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            wf = Workflow(
                name="保存测试",
                description="测试保存功能",
                start_url="https://save-test.com",
                tags=["test", "save"],
            )
            wf.steps.append(WorkflowStep(
                step_number=1,
                step_type="open",
                params={"url": "https://save-test.com"},
            ))
            
            wf.save(filepath)
            self.assertTrue(Path(filepath).exists())
            
            loaded = Workflow.load(filepath)
            self.assertEqual(loaded.name, "保存测试")
            self.assertEqual(len(loaded.steps), 1)
            self.assertEqual(loaded.tags, ["test", "save"])
        finally:
            os.unlink(filepath)


class TestWorkflowStep(unittest.TestCase):
    """工作流步骤测试"""

    def test_step_creation(self):
        """测试创建步骤"""
        step = WorkflowStep(
            step_number=1,
            step_type="click",
            params={"index": 2},
            description="点击第二个按钮",
        )
        
        self.assertEqual(step.step_number, 1)
        self.assertEqual(step.step_type, "click")
        self.assertEqual(step.params["index"], 2)
        self.assertEqual(step.description, "点击第二个按钮")
        
    def test_step_validation_rules(self):
        """测试步骤验证规则"""
        step = WorkflowStep(
            step_number=1,
            step_type="click",
            params={},
            validation={
                "url_contains": "/success",
                "element_exists": ".result",
            },
        )
        
        self.assertIn("url_contains", step.validation)
        self.assertEqual(step.validation["url_contains"], "/success")


class TestWorkflowRecorder(unittest.TestCase):
    """工作流录制器测试"""

    def test_recorder_initialization(self):
        """测试录制器初始化"""
        recorder = WorkflowRecorder(
            workflow_name="录制测试",
            description="测试录制",
            start_url="https://record.com",
        )
        
        self.assertEqual(recorder.workflow.name, "录制测试")
        self.assertEqual(recorder.current_step, 0)
        
    def test_record_step(self):
        """测试记录步骤"""
        recorder = WorkflowRecorder("测试", "描述", "https://test.com")
        
        fake_browser = MagicMock()
        fake_browser.get_state.return_value = MagicMock(
            url="https://test.com",
            title="Test",
            elements=[],
            get_clickable_elements=lambda: [],
            get_input_elements=lambda: [],
        )
        
        step = recorder.record_step(
            step_type="click",
            params={"index": 1},
            description="点击按钮",
            browser=fake_browser,
            snapshot=False,
        )
        
        self.assertEqual(recorder.current_step, 1)
        self.assertEqual(len(recorder.workflow.steps), 1)
        self.assertEqual(step.step_type, "click")
        self.assertEqual(step.step_number, 1)
        
    def test_finalize(self):
        """测试完成录制"""
        recorder = WorkflowRecorder("完成测试", "描述", "https://test.com")
        
        fake_browser = MagicMock()
        fake_browser.get_state.return_value = MagicMock(
            url="https://test.com",
            title="Test",
            elements=[],
            get_clickable_elements=lambda: [],
            get_input_elements=lambda: [],
        )
        
        recorder.record_step("open", {"url": "https://test.com"}, "打开页面", fake_browser, False)
        recorder.record_step("click", {"index": 1}, "点击", fake_browser, False)
        
        workflow = recorder.finalize()
        self.assertEqual(len(workflow.steps), 2)


class TestWorkflowPlayer(unittest.TestCase):
    """工作流播放器测试"""

    def test_player_initialization(self):
        """测试播放器初始化"""
        wf = Workflow("播放测试", "描述", "https://play.com")
        wf.steps.append(WorkflowStep(1, "open", {"url": "https://play.com"}))
        
        player = WorkflowPlayer(workflow=wf)
        
        self.assertEqual(player.workflow.name, "播放测试")
        self.assertEqual(len(player.results), 0)
        
    def test_resolve_params(self):
        """测试参数解析"""
        wf = Workflow("参数测试", "描述", "https://test.com")
        player = WorkflowPlayer(
            workflow=wf,
            parameters={"query": "OpenAI", "count": "5"},
        )
        
        params = player._resolve_params({
            "text": "搜索: ${query}",
            "limit": "${count}",
            "fixed": "不变",
        })
        
        self.assertEqual(params["text"], "搜索: OpenAI")
        self.assertEqual(params["limit"], "5")
        self.assertEqual(params["fixed"], "不变")
        
    def test_replace_variables(self):
        """测试变量替换"""
        wf = Workflow("变量测试", "描述", "https://test.com")
        wf.parameters = [
            {"name": "name", "default": "默认名"},
            {"name": "missing", "default": None},
        ]
        
        player = WorkflowPlayer(
            workflow=wf,
            parameters={"name": "实际名"},
        )
        
        text = "Hello ${name}, 欢迎${missing}使用"
        result = player._replace_variables(text)
        
        self.assertEqual(result, "Hello 实际名, 欢迎${missing}使用")


class TestWorkflowManager(unittest.TestCase):
    """工作流管理器测试"""

    def setUp(self):
        """设置临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = WorkflowManager.WORKFLOW_DIR
        WorkflowManager.WORKFLOW_DIR = Path(self.temp_dir)
        
    def tearDown(self):
        """清理临时目录"""
        WorkflowManager.WORKFLOW_DIR = self.original_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_list_workflows_empty(self):
        """测试空工作流列表"""
        manager = WorkflowManager()
        workflows = manager.list_workflows()
        self.assertEqual(len(workflows), 0)
        
    def test_save_and_load_workflow(self):
        """测试保存和加载"""
        manager = WorkflowManager()
        
        wf = Workflow("管理测试", "测试管理工作流", "https://manage.com")
        wf.steps.append(WorkflowStep(1, "open", {"url": "https://manage.com"}))
        
        filepath = manager.save_workflow(wf)
        self.assertTrue(Path(filepath).exists())
        
        workflows = manager.list_workflows()
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["name"], "管理测试")
        
        loaded = manager.load_workflow("管理测试")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "管理测试")
        
    def test_delete_workflow(self):
        """测试删除工作流"""
        manager = WorkflowManager()
        
        wf = Workflow("删除测试", "将被删除", "https://delete.com")
        manager.save_workflow(wf)
        
        self.assertTrue(manager.delete_workflow("删除测试"))
        self.assertIsNone(manager.load_workflow("删除测试"))
        self.assertFalse(manager.delete_workflow("不存在的"))


class TestStepType(unittest.TestCase):
    """步骤类型枚举测试"""

    def test_step_type_values(self):
        """测试步骤类型值"""
        self.assertEqual(StepType.CLICK.value, "click")
        self.assertEqual(StepType.INPUT.value, "input")
        self.assertEqual(StepType.OPEN.value, "open")
        self.assertEqual(StepType.DONE.value, "done")


if __name__ == "__main__":
    unittest.main()
