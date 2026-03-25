#!/usr/bin/env python3
"""
演示模式 - 模拟 IM 机器人工作流程
用于测试 Kimi API 和逻辑，不打开真实浏览器
"""
import os
import time
import base64
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

from src.platforms import get_platform
from src.vision_agent import KimiVisionAgent
from src.utils.logger import logger


class MockBrowserController:
    """模拟浏览器控制器"""
    
    def __init__(self):
        self.step = 0
        self.session_dir = Path("./demo_screenshots")
        self.session_dir.mkdir(exist_ok=True)
        
    def open(self, url, wait=3):
        logger.info(f"[模拟] 打开网页: {url}")
        return True
        
    def close(self):
        logger.info("[模拟] 关闭浏览器")
        return True
        
    def screenshot(self, filename):
        """生成模拟截图"""
        self.step += 1
        filepath = self.session_dir / filename
        
        # 创建模拟 WhatsApp/Telegram 界面
        img = Image.new('RGB', (1280, 800), color='#F0F0F0')
        draw = ImageDraw.Draw(img)
        
        # 左侧聊天列表
        draw.rectangle([0, 0, 400, 800], fill='#FFFFFF', outline='#E0E0E0')
        
        # 聊天项
        for i in range(5):
            y = 60 + i * 70
            # 头像
            draw.ellipse([20, y+10, 60, y+50], fill='#25D366' if i == 0 else '#CCC')
            # 名称
            draw.text((70, y+15), f"Chat {i+1}", fill='#000000')
            # 消息预览
            draw.text((70, y+35), f"Message preview...", fill='#666666')
            # 未读标记（第一个）
            if i == 0:
                draw.ellipse([370, y+15, 390, y+35], fill='#25D366')
                draw.text((378, y+20), "3", fill='#FFFFFF')
        
        # 右侧消息区域
        draw.rectangle([400, 0, 1280, 720], fill='#E5DDD5')
        
        # 消息气泡
        draw.rounded_rectangle([850, 100, 1250, 150], radius=10, fill='#DCF8C6')
        draw.text((860, 115), "Hello! How are you?", fill='#000000')
        
        draw.rounded_rectangle([420, 180, 820, 230], radius=10, fill='#FFFFFF')
        draw.text((430, 195), "I'm good, thanks!", fill='#000000')
        
        # 底部输入框
        draw.rectangle([400, 720, 1280, 800], fill='#F6F6F6')
        draw.rounded_rectangle([420, 735, 1200, 785], radius=20, fill='#FFFFFF')
        draw.text((440, 750), "Type a message...", fill='#999999')
        
        # 顶部状态栏
        draw.rectangle([400, 0, 1280, 60], fill='#075E54')
        draw.text((420, 20), "Test Chat", fill='#FFFFFF')
        
        # 添加步骤信息
        draw.text((10, 10), f"Step: {self.step}", fill='#000000')
        
        img.save(filepath)
        return str(filepath)
        
    def get_state(self):
        return {"elements": 15, "clickable": 8}
        
    def click(self, index, wait=2):
        logger.info(f"[模拟] 点击元素: {index}")
        return True
        
    def type_text(self, text, wait=1):
        logger.info(f"[模拟] 输入文本: {text[:30]}...")
        return True
        
    def input_to_element(self, index, text, wait=1):
        logger.info(f"[模拟] 在元素 {index} 输入: {text[:30]}...")
        return True
        
    def wait(self, seconds):
        time.sleep(seconds)


def run_demo(platform='whatsapp', max_steps=5):
    """运行演示"""
    logger.banner(f"IM 机器人演示模式 - {platform.upper()}")
    
    # 设置 API Key
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        logger.error("请设置 KIMI_API_KEY 环境变量")
        return
    
    # 初始化
    platform_obj = get_platform(platform)
    browser = MockBrowserController()
    vision = KimiVisionAgent()
    vision.set_system_prompt(platform_obj.get_system_prompt())
    
    logger.info(f"平台: {platform_obj.config.name}")
    logger.info(f"最大步数: {max_steps}")
    logger.info(f"API Key: {api_key[:15]}...")
    
    # 打开网页
    logger.info(f"\n打开 {platform_obj.config.url}...")
    browser.open(platform_obj.config.url)
    
    # 模拟登录等待
    logger.info("\n等待登录完成...")
    logger.info("(演示模式：跳过实际登录)")
    time.sleep(2)
    
    # 主循环
    logger.info("\n开始监控消息...")
    
    for step in range(1, max_steps + 1):
        logger.info(f"\n{'─' * 60}")
        logger.info(f"[步骤 {step}/{max_steps}]")
        
        # 截图
        screenshot_path = browser.screenshot(f"step_{step:03d}.png")
        logger.info(f"📸 截图: {screenshot_path}")
        
        # Kimi 分析
        logger.info("🧠 发送截图到 Kimi 分析...")
        try:
            decision = vision.analyze_screenshot(screenshot_path)
            logger.info(f"🎯 决策: {decision.action}")
            logger.info(f"💭 原因: {decision.reason}")
            logger.info(f"📋 参数: {decision.params}")
        except Exception as e:
            logger.error(f"Kimi 分析失败: {e}")
            continue
        
        # 执行操作
        if decision.action == 'click':
            browser.click(decision.params.get('index', 1))
        elif decision.action == 'input':
            browser.input_to_element(
                decision.params.get('index', 1),
                decision.params.get('text', '')
            )
        elif decision.action == 'wait':
            browser.wait(decision.params.get('seconds', 2))
        elif decision.action == 'done':
            logger.info("✅ 任务完成")
            break
        
        time.sleep(2)
    
    # 结束
    logger.info("\n" + "=" * 60)
    logger.info("演示结束")
    logger.info(f"截图保存在: {browser.session_dir}")
    browser.close()


if __name__ == "__main__":
    import sys
    platform = sys.argv[1] if len(sys.argv) > 1 else 'whatsapp'
    run_demo(platform, max_steps=5)
