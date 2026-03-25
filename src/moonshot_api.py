#!/usr/bin/env python3
"""
Moonshot API 辅助工具

- 验证 API Key
- 拉取最新模型列表
- 提供官方公告整理出的回退模型目录
"""
import json
from typing import Any, Dict, List, Optional
from urllib import error, request


CURATED_MODELS: List[Dict[str, Any]] = [
    {
        "id": "kimi-latest",
        "category": "general",
        "label": "Kimi Latest",
        "source": "curated",
        "released_at": "2025-02-17",
        "notes": "始终跟随 Kimi 智能助手当前最新模型，支持视觉能力。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-latest",
    },
    {
        "id": "kimi-thinking-preview",
        "category": "thinking",
        "label": "Kimi Thinking Preview",
        "source": "curated",
        "released_at": "2025-05-06",
        "notes": "多模态思考模型，适合复杂推理任务。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-thinking",
    },
    {
        "id": "kimi-k2-0905-preview",
        "category": "coding",
        "label": "Kimi K2 0905 Preview",
        "source": "curated",
        "released_at": "2025-09-05",
        "notes": "代码能力增强，支持 256K 上下文。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-k2-0905",
    },
    {
        "id": "kimi-k2-turbo-preview",
        "category": "coding",
        "label": "Kimi K2 Turbo Preview",
        "source": "curated",
        "released_at": "2025-09-16",
        "notes": "K2 高速版，输出速度更高。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/k2-prom",
    },
    {
        "id": "kimi-k2-thinking-turbo",
        "category": "thinking",
        "label": "Kimi K2 Thinking Turbo",
        "source": "curated",
        "released_at": "2025-11-06",
        "notes": "官方公告提到的最新 thinking turbo 型号。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/k2-turbo-discount",
    },
    {
        "id": "moonshot-v1-8k",
        "category": "legacy",
        "label": "Moonshot V1 8K",
        "source": "curated",
        "released_at": "2024-05-30",
        "notes": "经典稳定文本模型。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-api-quick-start-guide",
    },
    {
        "id": "moonshot-v1-32k",
        "category": "legacy",
        "label": "Moonshot V1 32K",
        "source": "curated",
        "released_at": "2024-05-30",
        "notes": "经典稳定长上下文文本模型。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-api-quick-start-guide",
    },
    {
        "id": "moonshot-v1-128k",
        "category": "legacy",
        "label": "Moonshot V1 128K",
        "source": "curated",
        "released_at": "2025-02-17",
        "notes": "旧版长上下文系列能力参考。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/kimi-latest",
    },
    {
        "id": "moonshot-v1-vision-preview",
        "category": "vision",
        "label": "Moonshot V1 Vision Preview",
        "source": "curated",
        "released_at": "2025-01-13",
        "notes": "官方变更记录提到的视觉预览模型。",
        "reference_url": "https://platform.moonshot.cn/blog/posts/changelog",
    },
]


def _normalize_base_url(base_url: str) -> str:
    """统一 API Base URL"""
    return base_url.rstrip("/")


def _request_json(url: str, api_key: str, timeout: int = 15) -> Dict[str, Any]:
    """发送 GET 请求并解析 JSON"""
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "im-bot-config-center/1.0",
        },
        method="GET",
    )

    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_curated_models() -> List[Dict[str, Any]]:
    """获取内置模型目录"""
    return [dict(item) for item in CURATED_MODELS]


def list_models(api_key: str, base_url: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """
    获取在线模型列表

    这里基于 OpenAI 兼容接口约定请求 `<base_url>/models`。
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API Key 不能为空")

    url = f"{_normalize_base_url(base_url)}/models"
    payload = _request_json(url, api_key=api_key, timeout=timeout)
    data = payload.get("data", [])

    models = []
    for item in data:
        model_id = item.get("id")
        if not model_id:
            continue
        models.append({
            "id": model_id,
            "object": item.get("object", "model"),
            "owned_by": item.get("owned_by", ""),
            "source": "live",
        })

    models.sort(key=lambda item: item["id"])
    return models


def validate_api_key(api_key: str, base_url: str, timeout: int = 15) -> Dict[str, Any]:
    """验证 API Key，并尽量附带模型列表"""
    try:
        models = list_models(api_key=api_key, base_url=base_url, timeout=timeout)
        return {
            "valid": True,
            "message": f"验证成功，可读取 {len(models)} 个模型",
            "models": models,
        }
    except ValueError as exc:
        return {
            "valid": False,
            "message": str(exc),
            "models": [],
        }
    except error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""

        message = f"请求失败: HTTP {exc.code}"
        if body:
            message = f"{message} - {body}"

        return {
            "valid": False,
            "message": message,
            "models": [],
            "status_code": exc.code,
        }
    except error.URLError as exc:
        return {
            "valid": False,
            "message": f"网络错误: {exc.reason}",
            "models": [],
        }
    except Exception as exc:
        return {
            "valid": False,
            "message": f"验证失败: {exc}",
            "models": [],
        }
