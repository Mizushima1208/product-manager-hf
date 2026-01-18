"""LLM-based equipment information extraction using Gemini."""
import base64
import json
import os
import re
import httpx
from typing import Optional

# Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDGGdodQ3_e_DS5zEzjIYEYOC5bPwf9ya8")

# Vision prompt - 建設機械・産業機器の銘板読み取り用
VISION_PROMPT = """この画像は建設機械や産業機器の銘板（ネームプレート）または本体の写真です。
以下の情報を読み取ってください。

以下のJSON形式で出力してください（他の文字は含めないでください）:
{
    "equipment_name": "機械名・製品名（例: プレートコンパクター、ランマー、発電機など）",
    "model_number": "型番・MODEL（例: MVH-R60, MT-55L など）",
    "manufacturer": "メーカー名（例: 三笠産業, MIKASA, マキタ など）",
    "serial_number": "シリアル番号・製造番号",
    "weight": "重量（kg）",
    "output_power": "出力（kW, ps, HP など）",
    "engine_model": "エンジン型式",
    "year_manufactured": "製造年",
    "specifications": "その他の仕様（読み取れた情報）"
}

注意:
- 銘板に書かれている情報を正確に読み取ってください
- 汚れや傷で読めない部分はnull
- 型番（MODEL）は最も重要な情報です
- メーカーは銘板のロゴや会社名から特定してください
- 三笠産業のロゴは三角形マークです
"""

# Text extraction prompt - OCRテキストから抽出
EXTRACTION_PROMPT = """以下は建設機械・産業機器の銘板のOCRテキストです。情報を抽出してください。

OCRテキスト:
{text}

以下のJSON形式で出力してください（他の文字は含めないでください）:
{{
    "equipment_name": "機械名・製品名",
    "model_number": "型番・MODEL",
    "manufacturer": "メーカー名",
    "serial_number": "シリアル番号",
    "weight": "重量（kg）",
    "output_power": "出力",
    "engine_model": "エンジン型式",
    "year_manufactured": "製造年",
    "specifications": "その他の仕様"
}}

注意:
- 見つからない項目はnull
- 型番（MODEL）を最優先で抽出
"""


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None


async def extract_from_image(image_bytes: bytes, api_key: str = None) -> Optional[dict]:
    """Extract product info directly from image using Gemini Vision."""
    key = api_key or GEMINI_API_KEY
    if not key:
        raise Exception("Gemini API Key が設定されていません。環境変数 GEMINI_API_KEY を設定してください。")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"

    # Encode image to base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    # Detect mime type (simple check)
    mime_type = "image/jpeg"
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        mime_type = "image/png"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        mime_type = "image/webp"

    payload = {
        "contents": [{
            "parts": [
                {"text": VISION_PROMPT},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)

        if response.status_code != 200:
            raise Exception(f"Gemini Vision API error: {response.status_code} - {response.text}")

        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return extract_json_from_response(text)


async def extract_with_gemini(ocr_text: str, api_key: str = None) -> Optional[dict]:
    """Extract product info using Google Gemini API (from OCR text)."""
    key = api_key or GEMINI_API_KEY
    if not key:
        raise Exception("Gemini API Key が設定されていません。環境変数 GEMINI_API_KEY を設定してください。")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"

    payload = {
        "contents": [{
            "parts": [{
                "text": EXTRACTION_PROMPT.format(text=ocr_text)
            }]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)

        if response.status_code != 200:
            raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return extract_json_from_response(text)


def format_extracted_info(extracted: dict) -> dict:
    """Format extracted info to match expected schema."""
    if not extracted:
        return None

    # Format weight
    weight = extracted.get("weight")
    if weight:
        weight_num = re.sub(r'[^\d\.]', '', str(weight))
        weight = f"{weight_num} kg" if weight_num else None

    return {
        "equipment_name": extracted.get("equipment_name"),
        "model_number": extracted.get("model_number"),
        "manufacturer": extracted.get("manufacturer"),
        "serial_number": extracted.get("serial_number"),
        "weight": weight,
        "output_power": extracted.get("output_power"),
        "engine_model": extracted.get("engine_model"),
        "year_manufactured": extracted.get("year_manufactured"),
        "specifications": extracted.get("specifications")
    }


async def get_available_llm_engines() -> list:
    """Get list of available LLM engines."""
    return [
        {
            "id": "gemini-vision",
            "name": "Gemini Vision（推奨）",
            "description": "画像から直接AI読み取り。最高精度",
            "available": True
        },
        {
            "id": "google-vision-gemini",
            "name": "Google Vision + Gemini",
            "description": "高精度OCR → AI解析の2段階処理",
            "available": True
        }
    ]
