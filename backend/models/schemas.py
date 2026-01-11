"""Pydantic schemas for API."""
from pydantic import BaseModel
from typing import Optional


class ProductItem(BaseModel):
    id: int
    product_name: Optional[str] = None
    model_number: Optional[str] = None
    manufacturer: Optional[str] = None
    price: Optional[str] = None
    jan_code: Optional[str] = None
    description: Optional[str] = None
    raw_text: str
    ocr_engine: str
    llm_engine: Optional[str] = None
    file_name: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
