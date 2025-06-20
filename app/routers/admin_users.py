from fastapi import APIRouter, HTTPException, Depends, Response
from typing import List
from pymongo import ReturnDocument
from bson import ObjectId
from app.core import security
from app.core.config import db
from app.models.user import UserOut

router = APIRouter(prefix="/admin/users", tags=["admin"])

@router.get("", response_model=List[UserOut])
def list_users(admin=Depends(security.get_current_admin)):
    users = []
    for u in db["users"].find():
        users.append(UserOut(**u, id=str(u["_id"])))
    return users

@router.put("/{id}/block", response_model=UserOut)
def block_or_unblock_user(id: str, block: bool = True, admin=Depends(security.get_current_admin)):
    oid = ObjectId(id)
    res = db["users"].find_one_and_update(
        {"_id": oid},
        {"$set": {"is_active": not block}},  # if block=True, set is_active=False
        return_document=ReturnDocument.AFTER
    )
    if not res:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(**res, id=id)


@router.delete("/{id}", status_code=204)
def delete_user(id: str, admin=Depends(security.get_current_admin)):
    result = db["users"].delete_one({"_id": ObjectId(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=204)


