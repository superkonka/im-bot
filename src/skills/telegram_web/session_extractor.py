#!/usr/bin/env python3
"""
Telegram Web Session 提取器

从已登录的 Telegram Web 浏览器中提取 MTProto session 数据，
转换为 Telethon 可用的 StringSession。

用法:
    .venv/bin/python src/skills/telegram_web/session_extractor.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import async_playwright

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

STATE_DIR = DATA_DIR / "telegram_web_state"
OUTPUT_DIR = DATA_DIR / "telegram_sessions"
OUTPUT_DIR.mkdir(exist_ok=True)


class SessionExtractor:
    """从 Telegram Web 浏览器中提取并转换 session"""

    URL = "https://web.telegram.org/k/"

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or (STATE_DIR / "telegram_web_state.json")

    async def extract(self) -> Optional[Dict[str, Any]]:
        """
        启动浏览器，加载已保存的状态，读取 localStorage 中的 session 数据。
        返回提取的原始数据字典，失败返回 None。
        """
        print("[Extractor] 启动浏览器...")
        p = await async_playwright().start()

        storage_state = None
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    storage_state = json.load(f)
                print(f"[Extractor] 已加载状态: {self.state_file}")
            except Exception as exc:
                print(f"[Extractor] 加载状态失败: {exc}")
                return None

        browser = await p.chromium.launch(
            headless=True,  # 提取过程无需可见
            args=["--disable-blink-features=AutomationControlled"],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            storage_state=storage_state,
        )

        page = await context.new_page()
        await page.goto(self.URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # 读取 localStorage
        print("[Extractor] 读取 localStorage...")
        local_storage = await page.evaluate("""() => {
            const result = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                result[key] = localStorage.getItem(key);
            }
            return result;
        }""")

        # 读取 sessionStorage
        print("[Extractor] 读取 sessionStorage...")
        session_storage = await page.evaluate("""() => {
            const result = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                result[key] = sessionStorage.getItem(key);
            }
            return result;
        }""")

        # 读取 IndexedDB（gramjs 可能把数据存在这里）
        print("[Extractor] 尝试读取 IndexedDB...")
        indexeddb_data = await self._read_indexeddb(page)

        await browser.close()
        await p.stop()

        # 合并所有数据
        result = {
            "localStorage": local_storage,
            "sessionStorage": session_storage,
            "indexedDB": indexeddb_data,
            "url": page.url,
        }

        # 保存原始数据供分析
        raw_path = OUTPUT_DIR / "web_session_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[Extractor] 原始数据已保存: {raw_path}")

        return result

    async def _read_indexeddb(self, page) -> Dict[str, Any]:
        """读取 IndexedDB 中的数据（gramjs 使用）"""
        try:
            return await page.evaluate("""
                async () => {
                    const result = {};
                    try {
                        const databases = await window.indexedDB.databases();
                        for (const dbInfo of databases) {
                            result[dbInfo.name] = { version: dbInfo.version, stores: {} };
                            try {
                                const db = await new Promise((resolve, reject) => {
                                    const request = window.indexedDB.open(dbInfo.name);
                                    request.onsuccess = () => resolve(request.result);
                                    request.onerror = () => reject(request.error);
                                });

                                for (const storeName of db.objectStoreNames) {
                                    const tx = db.transaction(storeName, 'readonly');
                                    const store = tx.objectStore(storeName);
                                    const allData = await new Promise((resolve, reject) => {
                                        const request = store.getAll();
                                        request.onsuccess = () => resolve(request.result);
                                        request.onerror = () => reject(request.error);
                                    });
                                    result[dbInfo.name].stores[storeName] = allData;
                                }
                            } catch (e) {
                                result[dbInfo.name].error = e.message;
                            }
                        }
                    } catch (e) {
                        result.error = e.message;
                    }
                    return result;
                }
            """)
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def analyze(data: Dict[str, Any]) -> None:
        """分析提取的数据，找出 session 相关键"""
        print("\n" + "=" * 60)
        print(" Session 数据分析")
        print("=" * 60)

        local = data.get("localStorage", {})
        print(f"\n📦 localStorage 键数: {len(local)}")

        # 找 session 相关键
        session_keys = [k for k in local.keys() if any(
            kw in k.lower() for kw in ["auth", "dc", "session", "key", "user"]
        )]
        print(f"\n🔑 疑似 session 相关键 ({len(session_keys)} 个):")
        for key in sorted(session_keys):
            value = local[key]
            preview = value[:100] if value else "(empty)"
            print(f"   {key}: {preview}...")

        # 检查是否有 base64 编码的 auth key
        for key in session_keys:
            value = local[key]
            if value and len(value) > 200:
                try:
                    decoded = base64.b64decode(value)
                    print(f"\n   ⚠️  {key} 可能是 base64 编码 (解码后 {len(decoded)} 字节)")
                    if len(decoded) == 256:
                        print(f"      → 256 字节！很可能是 auth_key")
                except Exception:
                    pass

        # 检查 dc
        dc_keys = [k for k in local.keys() if "dc" in k.lower()]
        if dc_keys:
            print(f"\n🌍 DC 相关键:")
            for k in dc_keys:
                print(f"   {k}: {local[k]}")

        # IndexedDB
        idb = data.get("indexedDB", {})
        if idb:
            print(f"\n🗄️  IndexedDB 数据库:")
            for db_name, db_info in idb.items():
                if "error" in db_info:
                    print(f"   {db_name}: 读取失败 ({db_info['error']})")
                else:
                    stores = db_info.get("stores", {})
                    print(f"   {db_name}: {list(stores.keys())}")

    @staticmethod
    def convert_to_telethon(data: Dict[str, Any]) -> Optional[str]:
        """
        尝试将 Web session 数据转换为 Telethon StringSession。

        返回 StringSession 字符串，失败返回 None。
        """
        local = data.get("localStorage", {})

        # 1. 找 dc_id
        dc_id = None
        for key, value in local.items():
            if key == "dc" or key == "dc_id":
                try:
                    dc_id = int(value)
                    break
                except (ValueError, TypeError):
                    continue
            if key.startswith("dc") and key[2:].isdigit() and "_auth" in key:
                dc_id = int(key[2:key.index("_")])
                break

        if dc_id is None:
            print("[Convert] 无法找到 dc_id")
            return None

        print(f"[Convert] 找到 dc_id: {dc_id}")

        # 2. 找 auth_key（Telegram Web K 版使用 hex 编码）
        auth_key = None
        auth_key_source = None
        for key, value in local.items():
            if "auth" in key.lower() and "key" in key.lower() and "fingerprint" not in key.lower():
                # localStorage 值可能被 JSON 包裹了引号，先清理
                clean_value = value.strip().strip('"').strip("'")

                # 尝试 hex 解码（Telegram Web K 版格式: 512 hex chars = 256 bytes）
                try:
                    decoded = bytes.fromhex(clean_value)
                    if len(decoded) == 256:
                        auth_key = decoded
                        auth_key_source = key
                        print(f"[Convert] 找到 auth_key (hex, {len(decoded)} bytes) from {key}")
                        break
                except Exception:
                    pass

                # 回退：尝试 base64 解码
                try:
                    decoded = base64.b64decode(clean_value)
                    if len(decoded) == 256:
                        auth_key = decoded
                        auth_key_source = key
                        print(f"[Convert] 找到 auth_key (base64, {len(decoded)} bytes) from {key}")
                        break
                except Exception:
                    continue

        if auth_key is None:
            print("[Convert] 无法找到 256 字节 auth_key")
            # 调试：打印所有候选值的长度
            for key, value in local.items():
                if "auth" in key.lower() and "key" in key.lower():
                    clean = value.strip().strip('"').strip("'")
                    print(f"   调试: {key} 原始长度={len(value)} 清理后={len(clean)}")
            return None

        # 3. 获取 DC IP 和端口
        dc_ips = {
            1: ("149.154.175.53", 443),
            2: ("149.154.167.51", 443),
            3: ("149.154.175.100", 443),
            4: ("149.154.167.91", 443),
            5: ("91.108.56.130", 443),
        }
        ip, port = dc_ips.get(dc_id, ("149.154.175.53", 443))
        print(f"[Convert] DC {dc_id} IP: {ip}:{port}")

        # 4. 构建 StringSession
        # Telethon StringSession 格式:
        #   1 byte: dc_id
        #   4 bytes: IP (as unsigned int, big-endian)
        #   2 bytes: port (big-endian)
        #   256 bytes: auth_key
        try:
            ip_parts = [int(x) for x in ip.split(".")]
            ip_packed = struct.pack(">BBBB", *ip_parts)
            port_packed = struct.pack(">H", port)

            session_bytes = bytes([dc_id]) + ip_packed + port_packed + auth_key
            session_string = base64.urlsafe_b64encode(session_bytes).decode("ascii").rstrip("=")

            print(f"[Convert] StringSession 生成成功!")
            print(f"   长度: {len(session_string)} 字符")
            print(f"   前 20 字符: {session_string[:20]}...")

            return session_string

        except Exception as exc:
            print(f"[Convert] 构建 StringSession 失败: {exc}")
            return None

    @staticmethod
    def save_session(session_string: str, filename: str = "telegram_web_session") -> Path:
        """保存 session 到文件"""
        path = OUTPUT_DIR / f"{filename}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(session_string)
        print(f"[Save] Session 已保存: {path}")
        return path


async def main():
    extractor = SessionExtractor()

    print("=" * 60)
    print(" Telegram Web Session 提取器")
    print("=" * 60)

    # 1. 提取数据
    data = await extractor.extract()
    if not data:
        print("❌ 提取失败")
        return 1

    # 2. 分析
    SessionExtractor.analyze(data)

    # 3. 尝试转换
    print("\n" + "=" * 60)
    print(" 转换为 Telethon StringSession")
    print("=" * 60)
    session_string = SessionExtractor.convert_to_telethon(data)

    if session_string:
        SessionExtractor.save_session(session_string)

        # 4. 验证
        print("\n" + "=" * 60)
        print(" 验证 session")
        print("=" * 60)
        await verify_session(session_string)
        return 0
    else:
        print("\n❌ 转换失败，需要手动分析 web_session_raw.json")
        return 1


async def verify_session(session_string: str) -> None:
    """用 Telethon 验证 session 是否有效"""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("⚠️ Telethon 未安装，跳过验证")
        return

    print("[Verify] 需要 api_id 和 api_hash 才能验证")
    print("[Verify] 你可以之后手动验证:")
    print()
    print("    from telethon import TelegramClient")
    print("    from telethon.sessions import StringSession")
    print(f"    client = TelegramClient(StringSession('{session_string[:30]}...'), api_id, api_hash)")
    print("    async with client:")
    print("        me = await client.get_me()")
    print("        print(me.first_name)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
