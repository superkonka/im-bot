#!/usr/bin/env python3
"""
测试 Vision Agent
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.config import get_app_config
from src.vision_agent import ActionDecision, KimiVisionAgent, extract_json_from_text
from src.use_cases import UseCaseDefinition, UseCaseValidationResult


class TestActionDecision(unittest.TestCase):
    
    def test_valid_action(self):
        decision = ActionDecision('click', {'index': 1}, 'test')
        self.assertTrue(decision.is_valid())
        
    def test_invalid_action(self):
        decision = ActionDecision('invalid', {}, 'test')
        self.assertFalse(decision.is_valid())
        
    def test_to_dict(self):
        decision = ActionDecision('wait', {'seconds': 3}, 'wait', 0.9)
        d = decision.to_dict()
        self.assertEqual(d['action'], 'wait')
        self.assertEqual(d['params']['seconds'], 3)


class TestExtractJson(unittest.TestCase):
    
    def test_plain_json(self):
        text = '{"action": "click", "params": {"index": 1}}'
        result = extract_json_from_text(text)
        self.assertEqual(result['action'], 'click')
        
    def test_markdown_json(self):
        text = '```json\n{"action": "wait"}\n```'
        result = extract_json_from_text(text)
        self.assertEqual(result['action'], 'wait')
        
    def test_invalid_json(self):
        text = 'not json'
        result = extract_json_from_text(text)
        self.assertIsNone(result)


class FakeCompletions:

    def __init__(self, content: str):
        self.content = content
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:

    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


class TestUseCases(unittest.TestCase):

    def test_use_case_definition_to_dict(self):
        use_case = UseCaseDefinition(
            case_id='login_whatsapp',
            name='WhatsApp login',
            objective='Confirm the user has logged in',
            pass_criteria=['chat list is visible'],
            fail_criteria=['QR code is visible'],
            allowed_next_actions=['proceed']
        )
        data = use_case.to_dict()
        self.assertEqual(data['case_id'], 'login_whatsapp')
        self.assertEqual(data['allowed_next_actions'], ['proceed'])

    def test_use_case_validation_result_from_dict(self):
        result = UseCaseValidationResult.from_dict({
            'case_id': 'login_whatsapp',
            'step_name': 'post_login',
            'status': 'pass',
            'confidence': 0.93,
            'matched_rules': ['chat list is visible'],
            'failed_rules': [],
            'evidence': ['message input is visible'],
            'reason': 'screen looks ready',
            'next_action': 'proceed',
        })
        self.assertEqual(result.status, 'pass')
        self.assertEqual(result.next_action, 'proceed')

    def test_build_use_case_prompt(self):
        agent = KimiVisionAgent(client=FakeClient('{}'))
        use_case = UseCaseDefinition(
            case_id='case_1',
            name='Login validation',
            objective='Make sure the app is ready',
            preconditions=['user already scanned QR'],
            pass_criteria=['chat list is visible'],
            fail_criteria=['QR code is visible'],
            allowed_next_actions=['proceed', 'review'],
            step_name='after_login',
            notes=['ignore transient toast messages'],
        )

        prompt = agent._build_use_case_validation_prompt(
            definition=use_case,
            step_name='after_login',
            context='Focus on the main panel'
        )

        self.assertIn('用例ID: case_1', prompt)
        self.assertIn('通过标准:', prompt)
        self.assertIn('Focus on the main panel', prompt)
        self.assertIn('"status": "pass|fail|uncertain"', prompt)

    def test_validate_use_case_success(self):
        fake_client = FakeClient(
            '{"status":"pass","confidence":0.91,"matched_rules":["chat list is visible"],'
            '"failed_rules":[],"evidence":["message input visible"],'
            '"reason":"main UI is loaded","next_action":"proceed"}'
        )
        agent = KimiVisionAgent(client=fake_client)

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'screen.png'
            image_path.write_bytes(b'fake-image')

            result = agent.validate_use_case(
                screenshot_path=str(image_path),
                use_case={
                    'case_id': 'login_whatsapp',
                    'name': 'WhatsApp login',
                    'pass_criteria': ['chat list is visible'],
                    'fail_criteria': ['QR code is visible'],
                },
                step_name='post_login'
            )

        self.assertEqual(result.case_id, 'login_whatsapp')
        self.assertEqual(result.status, 'pass')
        self.assertEqual(result.next_action, 'proceed')
        self.assertEqual(
            fake_client.chat.completions.last_kwargs['model'],
            get_app_config()['api']['kimi_vision_model']
        )

    def test_validate_use_case_invalid_json(self):
        agent = KimiVisionAgent(client=FakeClient('not-json'))

        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'screen.png'
            image_path.write_bytes(b'fake-image')

            result = agent.validate_use_case(
                screenshot_path=str(image_path),
                use_case=UseCaseDefinition(
                    case_id='case_uncertain',
                    name='Validation fallback'
                ),
            )

        self.assertEqual(result.status, 'uncertain')
        self.assertEqual(result.next_action, 'review')


if __name__ == '__main__':
    unittest.main()
