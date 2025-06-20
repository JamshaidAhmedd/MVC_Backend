from fastapi import APIRouter, HTTPException, Depends, Response
from bson import ObjectId
from app.core import security
from app.core.config import db
from app.models.category import CategoryIn, CategoryOut

router = APIRouter(prefix="/admin/categories", tags=["admin"])

@router.post("", response_model=CategoryOut, status_code=201)
def create_category(cat: CategoryIn, admin=Depends(security.get_current_admin)):
    if db["categories"].find_one({"name": cat.name}):
        raise HTTPException(status_code=400, detail="Category already exists")
    res = db["categories"].insert_one(cat.dict())
    return CategoryOut(id=str(res.inserted_id), **cat.dict())

@router.get("/{id}", response_model=CategoryOut)
def read_category(id: str, admin=Depends(security.get_current_admin)):
    cat = db["categories"].find_one({"_id": ObjectId(id)})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryOut(id=id, name=cat["name"], 
                       description=cat.get("description", ""), 
                       keywords=cat.get("keywords", []))


@router.put("/{id}", response_model=CategoryOut)
def update_category(id: str, cat: CategoryIn, admin=Depends(security.get_current_admin)):
    oid = ObjectId(id)
    result = db["categories"].find_one_and_update(
        {"_id": oid},
        {"$set": cat.dict()}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Category not found")
    return CategoryOut(id=id, **cat.dict())


@router.delete("/{id}", status_code=204)
def delete_category(id: str, admin=Depends(security.get_current_admin)):
    oid = ObjectId(id)
    cat = db["categories"].find_one_and_delete({"_id": oid})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    # Remove this category name from any courses' categories array
    db["courses"].update_many({}, {"$pull": {"categories": cat["name"]}})
    return Response(status_code=204)


