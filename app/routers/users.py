from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pymongo import ReturnDocument
from app.core import security
from app.core.config import db
from app.models.user import UserOut, UserUpdate, FavoriteIn

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserOut)
def get_profile(current_user = Depends(security.get_current_active_user)):
    # current_user is a dict from DB; convert to UserOut
    return UserOut(**current_user, id=str(current_user["_id"]))

@router.put("/me", response_model=UserOut)
def update_profile(data: UserUpdate, current_user = Depends(security.get_current_active_user)):
    update_data = {k: v for k, v in data.dict(exclude_none=True).items()}
    if update_data:
        db["users"].update_one({"_id": current_user["_id"]}, {"$set": update_data})
    updated = db["users"].find_one({"_id": current_user["_id"]})
    return UserOut(**updated, id=str(updated["_id"]))


@router.post("/me/favorites", status_code=200)
def add_favorite(fav: FavoriteIn, current_user = Depends(security.get_current_active_user)):
    updated = db["users"].find_one_and_update(
        {"_id": current_user["_id"]},
        {"$addToSet": {"favorites": fav.course_id}},
        return_document=ReturnDocument.AFTER
    )
    if not updated:
        raise HTTPException(404, "User not found")
    return {"favorites": updated["favorites"]}


@router.delete("/me/favorites/{course_id}", status_code=200)
def remove_favorite(course_id: str, current_user = Depends(security.get_current_active_user)):
    updated = db["users"].find_one_and_update(
        {"_id": current_user["_id"]},
        {"$pull": {"favorites": course_id}},
        return_document=ReturnDocument.AFTER
    )
    if not updated:
        raise HTTPException(404, "User not found")
    return {"favorites": updated["favorites"]}


@router.get("/me/notifications", response_model=List[dict])
def list_notifications(current_user = Depends(security.get_current_active_user)):
    user_doc = db["users"].find_one({"_id": current_user["_id"]}, {"notifications": 1})
    return user_doc.get("notifications", [])
