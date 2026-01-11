"""Equipment information extraction from nameplate images."""
from typing import Optional
from fastapi import HTTPException
from core import database
from .ocr import ocr_with_google_vision
from .llm_extractor import extract_with_gemini, extract_from_image, format_extracted_info


def has_valid_info(info: dict) -> bool:
    """Check if extracted info has any meaningful data."""
    if not info:
        return False
    # Check if at least one important field has value
    important_fields = ["equipment_name", "model_number", "manufacturer", "serial_number"]
    return any(info.get(field) for field in important_fields)


async def process_image_async(
    image_bytes: bytes,
    file_name: str = None,
    llm_engine: str = "gemini-vision"
) -> dict:
    """Process image with AI extraction.

    Args:
        image_bytes: Image data
        file_name: Original file name
        llm_engine:
            - "gemini-vision": Direct image analysis with Gemini (recommended)
            - "google-vision-gemini": Google Vision OCR + Gemini analysis
    """
    raw_text = ""
    extracted_info = None
    used_engine = llm_engine

    # Method 1: Gemini Vision - 画像から直接抽出
    if llm_engine == "gemini-vision":
        try:
            extracted = await extract_from_image(image_bytes)
            extracted_info = format_extracted_info(extracted)
            if has_valid_info(extracted_info):
                raw_text = "(Gemini Visionで画像から直接抽出)"
            else:
                print("Gemini Vision returned empty result, falling back to Google Vision + Gemini")
                used_engine = "google-vision-gemini"
        except Exception as e:
            print(f"Gemini Vision error: {e}, falling back to Google Vision + Gemini")
            used_engine = "google-vision-gemini"

    # Method 2: Google Vision OCR + Gemini Analysis
    if used_engine == "google-vision-gemini" and not has_valid_info(extracted_info):
        try:
            # Step 1: Google Vision OCR
            raw_text = ocr_with_google_vision(image_bytes)
            print(f"Google Vision OCR result: {raw_text[:200]}..." if len(raw_text) > 200 else f"Google Vision OCR result: {raw_text}")

            if raw_text:
                # Step 2: Gemini Analysis
                extracted = await extract_with_gemini(raw_text)
                extracted_info = format_extracted_info(extracted)

                if not has_valid_info(extracted_info):
                    print("Gemini analysis failed to extract meaningful info")
                    extracted_info = {}
            else:
                print("Google Vision OCR returned empty result")
                extracted_info = {}

        except HTTPException:
            raise
        except Exception as e:
            print(f"Google Vision + Gemini error: {e}")
            extracted_info = {}
            raw_text = f"(エラー: {str(e)})"

    # Create equipment record
    equipment_data = {
        "equipment_name": extracted_info.get("equipment_name") if extracted_info else None,
        "model_number": extracted_info.get("model_number") if extracted_info else None,
        "manufacturer": extracted_info.get("manufacturer") if extracted_info else None,
        "serial_number": extracted_info.get("serial_number") if extracted_info else None,
        "weight": extracted_info.get("weight") if extracted_info else None,
        "output_power": extracted_info.get("output_power") if extracted_info else None,
        "engine_model": extracted_info.get("engine_model") if extracted_info else None,
        "year_manufactured": extracted_info.get("year_manufactured") if extracted_info else None,
        "specifications": extracted_info.get("specifications") if extracted_info else None,
        "raw_text": raw_text,
        "ocr_engine": "google-vision" if used_engine == "google-vision-gemini" else "none",
        "llm_engine": used_engine if has_valid_info(extracted_info) else None,
        "file_name": file_name
    }

    return database.create_equipment(equipment_data)
