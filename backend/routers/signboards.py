"""Signboard (工事看板) management endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core import database

router = APIRouter(prefix="/api/signboards", tags=["signboards"])


class SignboardCreate(BaseModel):
    """Schema for creating signboard."""
    comment: str
    description: Optional[str] = None
    size: Optional[str] = None
    quantity: int = 1
    location: Optional[str] = None
    status: str = "在庫あり"
    notes: Optional[str] = None


class SignboardUpdate(BaseModel):
    """Schema for updating signboard."""
    comment: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None
    quantity: Optional[int] = None
    location: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class QuantityChange(BaseModel):
    """Schema for quantity change with reason."""
    amount: int
    reason: str


@router.get("")
async def get_signboards():
    """Get all signboards."""
    signboards = database.get_all_signboards()
    return {"signboards": signboards}


@router.get("/{signboard_id}")
async def get_signboard(signboard_id: int):
    """Get a specific signboard."""
    signboard = database.get_signboard(signboard_id)
    if not signboard:
        raise HTTPException(status_code=404, detail="Signboard not found")
    return signboard


@router.post("")
async def create_signboard(data: SignboardCreate):
    """Create a new signboard."""
    signboard = database.create_signboard(data.model_dump())
    return {"success": True, "signboard": signboard}


@router.put("/{signboard_id}")
async def update_signboard(signboard_id: int, data: SignboardUpdate):
    """Update signboard."""
    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return {"success": True, "signboard": existing}

    updated = database.update_signboard(signboard_id, updates)
    return {"success": True, "signboard": updated}


@router.delete("/{signboard_id}")
async def delete_signboard(signboard_id: int):
    """Delete signboard."""
    success = database.delete_signboard(signboard_id)
    if not success:
        raise HTTPException(status_code=404, detail="Signboard not found")
    return {"success": True}


@router.delete("")
async def delete_all_signboards():
    """Delete all signboards."""
    database.delete_all_signboards()
    return {"success": True}


@router.post("/{signboard_id}/increment")
async def increment_quantity(signboard_id: int):
    """Increment signboard quantity by 1."""
    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    new_quantity = (existing.get("quantity") or 0) + 1
    updated = database.update_signboard(signboard_id, {"quantity": new_quantity})
    return {"success": True, "signboard": updated}


@router.post("/{signboard_id}/decrement")
async def decrement_quantity(signboard_id: int):
    """Decrement signboard quantity by 1 (minimum 0)."""
    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    current = existing.get("quantity") or 0
    new_quantity = max(0, current - 1)
    updated = database.update_signboard(signboard_id, {"quantity": new_quantity})
    return {"success": True, "signboard": updated}


@router.post("/{signboard_id}/add")
async def add_quantity(signboard_id: int, data: QuantityChange):
    """Add quantity with reason (required)."""
    if not data.reason or not data.reason.strip():
        raise HTTPException(status_code=400, detail="理由を入力してください")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="追加する数量は1以上にしてください")

    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    quantity_before = existing.get("quantity") or 0
    quantity_after = quantity_before + data.amount

    # Update quantity
    updated = database.update_signboard(signboard_id, {"quantity": quantity_after})

    # Record history
    database.create_quantity_history(
        signboard_id=signboard_id,
        change_type="add",
        change_amount=data.amount,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        reason=data.reason.strip()
    )

    return {"success": True, "signboard": updated}


@router.post("/{signboard_id}/subtract")
async def subtract_quantity(signboard_id: int, data: QuantityChange):
    """Subtract quantity with reason (required)."""
    if not data.reason or not data.reason.strip():
        raise HTTPException(status_code=400, detail="理由を入力してください")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="減少する数量は1以上にしてください")

    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    quantity_before = existing.get("quantity") or 0
    quantity_after = max(0, quantity_before - data.amount)

    # Update quantity
    updated = database.update_signboard(signboard_id, {"quantity": quantity_after})

    # Record history
    database.create_quantity_history(
        signboard_id=signboard_id,
        change_type="subtract",
        change_amount=data.amount,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        reason=data.reason.strip()
    )

    return {"success": True, "signboard": updated}


@router.get("/{signboard_id}/history")
async def get_signboard_history(signboard_id: int):
    """Get quantity change history for a signboard."""
    existing = database.get_signboard(signboard_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Signboard not found")

    history = database.get_quantity_history_by_signboard(signboard_id)
    return {"history": history}


@router.get("/history/all")
async def get_all_history():
    """Get all quantity change history."""
    history = database.get_all_quantity_history()
    return {"history": history}


@router.post("/reset-all-quantities")
async def reset_all_quantities():
    """Reset all signboard quantities to 0 and clear history."""
    signboards = database.get_all_signboards()
    reset_count = 0

    for signboard in signboards:
        if signboard.get("quantity", 0) != 0:
            database.update_signboard(signboard["id"], {"quantity": 0})
            reset_count += 1

    # Clear all quantity history
    database.clear_all_quantity_history()

    return {
        "success": True,
        "message": f"{reset_count}件の看板をリセットしました",
        "reset_count": reset_count
    }
