#!/usr/bin/env python3
"""
浏览器控制器 - 使用 Playwright
更稳定可靠的浏览器自动化
"""
import time
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from playwright.sync_api import sync_playwright, Page, Browser

from .utils.logger import logger
from .config import get_app_config


@dataclass
class Element:
    """页面元素"""
    index: int
    tag: str
    text: str
    clickable: bool = False
    input_field: bool = False
    selector: str = ""


@dataclass
class PageState:
    """页面状态"""
    url: str
    title: str
    elements: List[Element]
    
    def get_clickable_elements(self) -> List[Element]:
        """获取可点击元素"""
        return [e for e in self.elements if e.clickable]
    
    def get_input_elements(self) -> List[Element]:
        """获取输入框元素"""
        return [e for e in self.elements if e.input_field]


class BrowserController:
    """浏览器控制器 - Playwright 实现"""
    
    def __init__(self, headless: Optional[bool] = None):
        app_config = get_app_config()
        browser_config = app_config["browser"]

        self.headless = browser_config["headless"] if headless is None else headless
        self.timeout = browser_config["timeout"]
        self.viewport = {
            'width': browser_config["viewport_width"],
            'height': browser_config["viewport_height"],
        }
        self.launch_args = list(browser_config["launch_args"])
        self.current_url = ""
        self.is_open = False
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        
    def open(self, url: str, wait: int = 3) -> bool:
        """打开网页"""
        logger.info(f"打开网页: {url}")
        
        try:
            self._playwright = sync_playwright().start()
            
            # 启动浏览器
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=self.launch_args
            )
            
            # 创建上下文和页面
            context = self._browser.new_context(viewport=self.viewport)
            
            self._page = context.new_page()
            self._page.set_default_timeout(self.timeout * 1000)
            self._page.goto(url)
            
            self.current_url = url
            self.is_open = True
            
            time.sleep(wait)
            logger.info("浏览器已打开")
            return True
            
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")
            return False
    
    def close(self) -> bool:
        """关闭浏览器"""
        logger.info("关闭浏览器")
        
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
            
            self.is_open = False
            return True
            
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")
            return False
    
    def screenshot(self, filepath: Optional[str] = None) -> str:
        """截图"""
        if not self._page:
            logger.error("浏览器未打开")
            return ""
        
        if filepath is None:
            filepath = "screenshot.png"
        
        try:
            self._page.screenshot(path=filepath, full_page=False)
            logger.debug(f"截图已保存: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return ""
    
    def get_state(self) -> PageState:
        """获取页面状态（可交互元素列表）"""
        if not self._page:
            return PageState(url="", title="", elements=[])
        
        try:
            url = self._page.url
            title = self._page.title()
            
            # 获取所有可交互元素
            elements = []
            
            # 查找按钮、链接、输入框等
            selectors = [
                'button',
                'a',
                'input[type="text"]',
                'input[type="search"]',
                'textarea',
                '[role="button"]',
                '[clickable]',
            ]
            
            idx = 1
            for selector in selectors:
                try:
                    locators = self._page.locator(selector).all()
                    for loc in locators:
                        try:
                            if loc.is_visible() and loc.is_enabled():
                                text = loc.inner_text() or loc.get_attribute('aria-label') or ""
                                text = text.strip()[:50]  # 截断
                                
                                is_clickable = selector in ['button', 'a', '[role="button"]'] or loc.is_enabled()
                                is_input = selector in ['input[type="text"]', 'input[type="search"]', 'textarea']
                                
                                elements.append(Element(
                                    index=idx,
                                    tag=selector.split('[')[0],
                                    text=text,
                                    clickable=is_clickable,
                                    input_field=is_input,
                                    selector=selector
                                ))
                                idx += 1
                        except:
                            continue
                except:
                    continue
            
            return PageState(url=url, title=title, elements=elements)
            
        except Exception as e:
            logger.error(f"获取页面状态失败: {e}")
            return PageState(url="", title="", elements=[])
    
    def click(self, index: int, wait: int = 2) -> bool:
        """点击元素（通过索引）"""
        logger.debug(f"点击元素: {index}")
        
        if not self._page:
            return False
        
        try:
            state = self.get_state()
            if 1 <= index <= len(state.elements):
                element = state.elements[index - 1]
                # 使用 JavaScript 点击
                self._page.evaluate(f"document.querySelectorAll('{element.selector}')[{index-1}].click()")
                time.sleep(wait)
                return True
            else:
                logger.warning(f"元素索引 {index} 超出范围")
                return False
                
        except Exception as e:
            logger.error(f"点击失败: {e}")
            return False
    
    def click_by_text(self, text: str, wait: int = 2, timeout_ms: int = 3000) -> bool:
        """通过文本点击元素"""
        logger.debug(f"点击文本: {text}")
        
        if not self._page:
            return False
        
        try:
            # 尝试多种方式点击
            try:
                self._page.get_by_text(text, exact=False).click(timeout=timeout_ms)
                time.sleep(wait)
                return True
            except:
                pass
            
            # 使用 contains 文本
            try:
                self._page.locator(f"text={text}").first.click(timeout=timeout_ms)
                time.sleep(wait)
                return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"点击失败: {e}")
            return False

    def click_by_selector(self, selector: str, wait: int = 2, timeout_ms: int = 3000) -> bool:
        """通过选择器点击元素"""
        logger.debug(f"点击选择器: {selector}")

        if not self._page:
            return False

        try:
            self._page.locator(selector).first.click(timeout=timeout_ms)
            time.sleep(wait)
            return True

        except Exception as e:
            logger.error(f"点击选择器失败: {e}")
            return False

    def click_selector_by_text(self, selector: str, text: str, wait: int = 2, timeout_ms: int = 3000) -> bool:
        """在指定选择器范围内按文本点击元素"""
        logger.debug(f"点击选择器文本: {selector} -> {text}")

        if not self._page:
            return False

        try:
            locator = self._page.locator(selector).filter(has_text=text).first
            locator.click(timeout=timeout_ms)
            time.sleep(wait)
            return True

        except Exception as e:
            logger.error(f"按选择器文本点击失败: {e}")
            return False

    def click_visible_text_via_js(
        self,
        text: str,
        wait: int = 2,
        left_panel_only: bool = False,
    ) -> bool:
        """通过页面脚本点击可见文本，适合处理定位器不稳定的页面"""
        logger.debug(f"通过 JS 点击文本: {text}")

        if not self._page:
            return False

        try:
            clicked = self._page.evaluate(
                """
                ({ needle, leftPanelOnly }) => {
                  const normalizedNeedle = (needle || "").trim();
                  if (!normalizedNeedle) return false;

                  const isVisible = (el) => {
                    if (!el || !(el instanceof Element)) return false;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === "hidden" || style.display === "none") return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                  };

                  const isLeftPanelCandidate = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.left >= 0 && rect.left < window.innerWidth * 0.42;
                  };

                  const clickableAncestor = (el) => {
                    let current = el;
                    while (current && current !== document.body) {
                      const tag = (current.tagName || "").toLowerCase();
                      if (
                        current.getAttribute("role") === "button" ||
                        ["a", "button"].includes(tag) ||
                        typeof current.onclick === "function"
                      ) {
                        return current;
                      }
                      current = current.parentElement;
                    }
                    return el;
                  };

                  const candidates = Array.from(document.querySelectorAll("div, span, a, button"))
                    .filter((el) => {
                      if (!isVisible(el)) return false;
                      if (leftPanelOnly && !isLeftPanelCandidate(el)) return false;
                      const textValue = (el.innerText || "").trim();
                      if (!textValue) return false;
                      return textValue === normalizedNeedle || textValue.includes(normalizedNeedle);
                    })
                    .sort((a, b) => {
                      const aRect = a.getBoundingClientRect();
                      const bRect = b.getBoundingClientRect();
                      if (aRect.top !== bRect.top) return aRect.top - bRect.top;
                      return aRect.left - bRect.left;
                    });

                  for (const candidate of candidates) {
                    const target = clickableAncestor(candidate);
                    if (!isVisible(target)) continue;
                    target.scrollIntoView({ block: "center", inline: "nearest" });
                    const rect = target.getBoundingClientRect();
                    const x = rect.left + Math.min(rect.width / 2, 24);
                    const y = rect.top + rect.height / 2;
                    const elementAtPoint = document.elementFromPoint(x, y);
                    const clickTarget = elementAtPoint && target.contains(elementAtPoint) ? elementAtPoint : target;
                    ["pointerdown", "mousedown", "mouseup", "click"].forEach((type) => {
                      clickTarget.dispatchEvent(new MouseEvent(type, {
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                        clientX: x,
                        clientY: y,
                      }));
                    });
                    return true;
                  }

                  return false;
                }
                """,
                {"needle": text, "leftPanelOnly": left_panel_only},
            )
            if clicked:
                time.sleep(wait)
                return True
            return False
        except Exception as e:
            logger.error(f"JS 文本点击失败: {e}")
            return False
    
    def type_text(self, text: str, wait: int = 1) -> bool:
        """在当前焦点元素输入文本"""
        logger.debug(f"输入文本: {text[:30]}...")
        
        if not self._page:
            return False
        
        try:
            self._page.keyboard.type(text)
            time.sleep(wait)
            return True
            
        except Exception as e:
            logger.error(f"输入失败: {e}")
            return False
    
    def input_to_element(self, index: int, text: str, wait: int = 1) -> bool:
        """点击元素并输入文本"""
        logger.debug(f"在元素 {index} 输入: {text[:30]}...")
        
        if not self._page:
            return False
        
        try:
            # 先点击元素
            if self.click(index, wait=1):
                # 清除并输入
                self._page.keyboard.press("Control+a")
                self._page.keyboard.press("Delete")
                self._page.keyboard.type(text)
                time.sleep(wait)
                return True
            return False
            
        except Exception as e:
            logger.error(f"输入失败: {e}")
            return False
    
    def input_by_selector(self, selector: str, text: str, wait: int = 1, timeout_ms: int = 3000) -> bool:
        """通过选择器输入文本"""
        logger.debug(f"在 {selector} 输入: {text[:30]}...")
        
        if not self._page:
            return False
        
        try:
            locator = self._page.locator(selector).first
            locator.click(timeout=timeout_ms)
            try:
                locator.fill(text)
            except Exception:
                self._page.keyboard.press("Control+a")
                self._page.keyboard.press("Delete")
                self._page.keyboard.type(text)
            time.sleep(wait)
            return True
            
        except Exception as e:
            logger.error(f"输入失败: {e}")
            return False
    
    def press_key(self, key: str, wait: int = 1) -> bool:
        """按下键盘按键"""
        logger.debug(f"按下按键: {key}")
        
        if not self._page:
            return False
        
        try:
            self._page.keyboard.press(key)
            time.sleep(wait)
            return True
            
        except Exception as e:
            logger.error(f"按键失败: {e}")
            return False
    
    def wait(self, seconds: int) -> None:
        """等待"""
        logger.debug(f"等待 {seconds} 秒")
        time.sleep(seconds)
    
    def get_page(self) -> Optional[Page]:
        """获取 Playwright Page 对象（高级用法）"""
        return self._page

    def get_texts_by_selector(self, selector: str) -> List[str]:
        """获取选择器匹配元素的文本列表"""
        if not self._page:
            return []

        texts: List[str] = []
        try:
            locator = self._page.locator(selector)
            count = locator.count()
            for idx in range(count):
                try:
                    text = locator.nth(idx).inner_text().strip()
                    if text:
                        texts.append(text)
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"读取文本失败: {e}")

        return texts

    def get_first_text_by_selector(self, selector: str) -> str:
        """获取选择器匹配到的第一个非空文本"""
        texts = self.get_texts_by_selector(selector)
        for text in texts:
            normalized = text.strip()
            if normalized:
                return normalized
        return ""

    def get_message_items(self, selector: str, limit: int = 12) -> List[Dict[str, Any]]:
        """读取消息列表，并尽量推断消息角色"""
        if not self._page:
            return []

        try:
            payload = self._page.evaluate(
                """
                ({ selector, limit }) => {
                  const nodes = Array.from(document.querySelectorAll(selector));
                  return nodes
                    .map((node) => {
                      const text = (node.innerText || "").trim();
                      if (!text) return null;

                      const own = node.closest("[class]") || node;
                      const markers = [
                        typeof node.className === "string" ? node.className : "",
                        typeof own.className === "string" ? own.className : "",
                        node.getAttribute("data-testid") || "",
                        node.getAttribute("aria-label") || "",
                      ].join(" ").toLowerCase();

                      let role = "unknown";
                      if (/(own|outgoing|message-out|is-out|my-message|from-me)/.test(markers)) {
                        role = "assistant";
                      } else if (/(incoming|message-in|is-in|peer-message|from-peer)/.test(markers)) {
                        role = "user";
                      }

                      return { text, role };
                    })
                    .filter(Boolean)
                    .slice(-limit);
                }
                """,
                {"selector": selector, "limit": max(limit, 1)},
            )
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
        except Exception as e:
            logger.error(f"读取消息列表失败: {e}")

        return []

    def is_page_alive(self) -> bool:
        """页面是否仍然可用"""
        if not self._page:
            return False

        try:
            return not self._page.is_closed()
        except Exception:
            return False

    def has_visible_selector(self, selector: str, timeout_ms: int = 1000) -> bool:
        """判断选择器是否有可见元素"""
        if not self._page:
            return False

        try:
            locator = self._page.locator(selector).first
            return locator.is_visible(timeout=timeout_ms)
        except Exception:
            return False
