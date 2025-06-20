#!/usr/bin/env python3
"""
app.py

Phase 3 – Course Search, Detail, Categories, Users, Favorites & Notifications
"""

import os
import math
import threading
from typing import List, Optional
from datetime import timedelta

from bson import ObjectId
from fastapi import (
    FastAPI, HTTPException, Depends, status,
    Query, Path
)
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from pymongo import MongoClient, TEXT

from core import security
import category_tagger
import keyword_queue
import notifications

# ── CONFIG ────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://admin:admin@cluster0.hpskmws.mongodb.net/course_app?retryWrites=true&w=majority"
)
ALPHA = 0.7    # text vs sentiment
BETA  = 0.2    # popularity (#reviews)
# ── END CONFIG ────────────────────────────────────────────────────────────

# ── DB SETUP ─────────────────────────────────────────────────────────────
client      = MongoClient(MONGO_URI)
db          = client["course_app"]
courses_col = db["courses"]
cats_col    = db["categories"]
users_col   = db["users"]

# ── Pydantic / Response Models ───────────────────────────────────────────
class CourseResult(BaseModel):
    course_id: str
    title: str
    ranking_score: float
    text_norm: float
    sent_norm: float
    pop_weight: float
    num_reviews: int
    smoothed_sentiment: float

class Review(BaseModel):
    review_id: str
    text: str
    rating: Optional[float]
    sentiment_score: Optional[float]

class CourseDetail(BaseModel):
    course_id: str
    title: str
    description: str
    provider: str
    url: str
    categories: List[str]
    num_reviews: int
    avg_sentiment: float
    smoothed_sentiment: float
    reviews: List[Review]

class CategoryIn(BaseModel):
    name: str
    description: str = ""
    keywords: List[str]

class CategoryOut(CategoryIn):
    id: str

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    email: EmailStr
    full_name: Optional[str] = None

class UserOut(BaseModel):
    id: str
    username: str
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    favorites: List[str]
    notifications: List[dict]

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class FavoriteIn(BaseModel):
    course_id: str

# ── APP ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Course + Category + User API",
    version="1.0",
    description="Search, categories, authentication, favorites & notifications"
)

#
# — AUTH & USER MANAGEMENT —
#

@app.post("/users/register", response_model=UserOut, summary="Signup (UC-8)")
def register(u: UserRegister):
    if users_col.find_one({"username": u.username}):
        raise HTTPException(400, "Username taken")
    if users_col.find_one({"email": u.email}):
        raise HTTPException(400, "Email already used")
    doc = {
        "username": u.username,
        "email": u.email,
        "full_name": u.full_name,
        "hashed_password": security.get_password_hash(u.password),
        "is_active": True,
        "is_admin": False,
        "favorites": [],
        "notifications": []
    }
    res = users_col.insert_one(doc)
    return UserOut(
        id=str(res.inserted_id),
        username=u.username,
        email=u.email,
        full_name=u.full_name,
        is_active=True,
        is_admin=False,
        favorites=[],
        notifications=[]
    )

@app.post("/users/login", response_model=Token, summary="Login (UC-9)")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = security.authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = security.create_access_token(
        data={"sub": user["username"], "user_id": str(user["_id"])},
        expires_delta=timedelta(hours=4)
    )
    return {"access_token": token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserOut, summary="Get own profile (UC-10)")
def read_profile(u=Depends(security.get_current_active_user)):
    return UserOut(
        id=str(u["_id"]),
        username=u["username"],
        email=u["email"],
        full_name=u.get("full_name"),
        is_active=u["is_active"],
        is_admin=u["is_admin"],
        favorites=u.get("favorites", []),
        notifications=u.get("notifications", [])
    )

@app.put("/users/me", response_model=UserOut, summary="Update own profile (UC-10)")
def update_profile(update: UserRegister, u=Depends(security.get_current_active_user)):
    users_col.update_one(
        {"_id": u["_id"]},
        {"$set": {"email": update.email, "full_name": update.full_name}}
    )
    u2 = users_col.find_one({"_id": u["_id"]})
    return UserOut(
        id=str(u2["_id"]), username=u2["username"], email=u2["email"],
        full_name=u2.get("full_name"), is_active=u2["is_active"],
        is_admin=u2["is_admin"], favorites=u2.get("favorites", []),
        notifications=u2.get("notifications", [])
    )

@app.get("/admin/users", response_model=List[UserOut], summary="List all users (UC-7)")
def list_users(_=Depends(security.get_current_admin)):
    out = []
    for u in users_col.find():
        out.append(UserOut(
            id=str(u["_id"]), username=u["username"], email=u["email"],
            full_name=u.get("full_name"), is_active=u["is_active"],
            is_admin=u["is_admin"], favorites=u.get("favorites", []),
            notifications=u.get("notifications", [])
        ))
    return out

@app.put("/admin/users/{id}/block", response_model=UserOut, summary="Block/unblock user (UC-7)")
def block_user(
    id: str,
    block: bool = Query(..., description="true=block, false=unblock"),
    _=Depends(security.get_current_admin)
):
    oid = ObjectId(id)
    res = users_col.update_one({"_id": oid}, {"$set": {"is_active": not block}})
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    u = users_col.find_one({"_id": oid})
    return UserOut(
        id=str(u["_id"]), username=u["username"], email=u["email"],
        full_name=u.get("full_name"), is_active=u["is_active"],
        is_admin=u["is_admin"], favorites=u.get("favorites", []),
        notifications=u.get("notifications", [])
    )

@app.delete("/admin/users/{id}", status_code=204, summary="Delete user (UC-7)")
def delete_user(id: str, _=Depends(security.get_current_admin)):
    res = users_col.delete_one({"_id": ObjectId(id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "User not found")

#
# — FAVORITES & NOTIFICATIONS (UC-11,12) —
#

@app.post(
    "/users/me/favorites",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add favorite (UC-11)"
)
def add_favorite(fav: FavoriteIn, u=Depends(security.get_current_active_user)):
    users_col.update_one({"_id": u["_id"]}, {"$addToSet": {"favorites": fav.course_id}})

@app.delete(
    "/users/me/favorites/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove favorite (UC-11)"
)
def remove_favorite(course_id: str, u=Depends(security.get_current_active_user)):
    users_col.update_one({"_id": u["_id"]}, {"$pull": {"favorites": course_id}})

@app.get(
    "/users/me/notifications",
    response_model=List[dict],
    summary="List notifications (UC-12)"
)
def list_notifications(u=Depends(security.get_current_active_user)):
    u2 = users_col.find_one({"_id": u["_id"]}, {"notifications": 1})
    return u2.get("notifications", [])

#
# — COURSES & CATEGORIES —
#

@app.get("/search", response_model=List[CourseResult], summary="Search & rank")
def search(
    query: str = Query(..., min_length=1),
    top_k: int  = Query(10, ge=1, le=100),
    u: Optional[dict] = Depends(security.get_current_user)  # optional
):
    cursor = courses_col.find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"},
         "course_id": 1, "title": 1, "smoothed_sentiment": 1, "num_reviews": 1}
    ).sort([("score", {"$meta": "textScore"})]).limit(top_k * 5)
    docs = list(cursor)
    if not docs:
        # queue a miss for later notification
        if u:
            keyword_queue.add_request(u["_id"], query)
        return []

    max_score = max(d.get("score", 0) for d in docs) or 1.0
    out = []
    for d in docs:
        tn = d["score"] / max_score
        sent = float(d.get("smoothed_sentiment") or 0.0)
        sn = (sent + 1) / 2
        n = int(d.get("num_reviews") or 0)
        pw = math.log(1 + n)
        score = ALPHA * tn + (1 - ALPHA) * sn + BETA * pw
        out.append(CourseResult(
            course_id=d["course_id"], title=d["title"],
            ranking_score=round(score, 4),
            text_norm=round(tn, 4),
            sent_norm=round(sn, 4),
            pop_weight=round(pw, 4),
            num_reviews=n,
            smoothed_sentiment=round(sent, 4)
        ))
    out.sort(key=lambda r: r.ranking_score, reverse=True)
    return out[:top_k]

@app.get("/course/{course_id}", response_model=CourseDetail, summary="Course detail")
def get_course(course_id: str = Path(...)):
    doc = courses_col.find_one({"course_id": course_id})
    if not doc:
        raise HTTPException(404, f"Course '{course_id}' not found")
    reviews = []
    for r in doc.get("reviews", []):
        try:
            rating = float(r.get("rating"))
        except:
            rating = None
        try:
            sent = float(r.get("sentiment_score"))
        except:
            sent = None
        reviews.append(Review(
            review_id=r.get("review_id", ""),
            text=r.get("text", ""),
            rating=rating,
            sentiment_score=sent
        ))
    return CourseDetail(
        course_id=doc["course_id"],
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        provider=doc.get("provider", ""),
        url=doc.get("url", ""),
        categories=doc.get("categories", []),
        num_reviews=int(doc.get("num_reviews") or 0),
        avg_sentiment=float(doc.get("avg_sentiment") or 0.0),
        smoothed_sentiment=float(doc.get("smoothed_sentiment") or 0.0),
        reviews=reviews
    )

@app.get("/categories", response_model=List[CategoryOut], summary="List categories")
def list_categories():
    return [
        CategoryOut(
            id=str(c["_id"]),
            name=c["name"],
            description=c.get("description", ""),
            keywords=c.get("keywords", [])
        )
        for c in cats_col.find()
    ]

@app.get("/categories/{name}/courses", response_model=List[CourseResult], summary="Browse by category")
def courses_by_category(name: str):
    docs = courses_col.find(
        {"categories": name},
        {"course_id": 1, "title": 1, "smoothed_sentiment": 1, "num_reviews": 1}
    )
    results = []
    for d in docs:
        sent = float(d.get("smoothed_sentiment") or 0.0)
        sn = (sent + 1) / 2
        n = int(d.get("num_reviews") or 0)
        pw = math.log(1 + n)
        score = ALPHA * 0 + (1 - ALPHA) * sn + BETA * pw
        results.append(CourseResult(
            course_id=d["course_id"],
            title=d["title"],
            ranking_score=round(score, 4),
            text_norm=0.0,
            sent_norm=round(sn, 4),
            pop_weight=round(pw, 4),
            num_reviews=n,
            smoothed_sentiment=round(sent, 4)
        ))
    results.sort(key=lambda r: r.ranking_score, reverse=True)
    return results

@app.post("/admin/categories", response_model=CategoryOut, summary="Create category")
def create_category(cat: CategoryIn, _=Depends(security.get_current_admin)):
    if cats_col.find_one({"name": cat.name}):
        raise HTTPException(400, "Category already exists")
    res = cats_col.insert_one(cat.dict())
    return CategoryOut(id=str(res.inserted_id), **cat.dict())

@app.get("/admin/categories/{id}", response_model=CategoryOut, summary="Get category")
def get_category(id: str, _=Depends(security.get_current_admin)):
    c = cats_col.find_one({"_id": ObjectId(id)})
    if not c:
        raise HTTPException(404, "Category not found")
    return CategoryOut(
        id=id,
        name=c["name"],
        description=c.get("description", ""),
        keywords=c.get("keywords", [])
    )

@app.put("/admin/categories/{id}", response_model=CategoryOut, summary="Update category")
def update_category(id: str, cat: CategoryIn, _=Depends(security.get_current_admin)):
    oid = ObjectId(id)
    if not cats_col.find_one({"_id": oid}):
        raise HTTPException(404, "Category not found")
    cats_col.update_one({"_id": oid}, {"$set": cat.dict()})
    return CategoryOut(id=id, **cat.dict())

@app.delete("/admin/categories/{id}", status_code=204, summary="Delete category")
def delete_category(id: str, _=Depends(security.get_current_admin)):
    oid = ObjectId(id)
    cat = cats_col.find_one_and_delete({"_id": oid})
    if not cat:
        raise HTTPException(404, "Category not found")
    courses_col.update_many({}, {"$pull": {"categories": cat["name"]}})

#
# ── STARTUP HOOKS ────────────────────────────────────────────────────────
#

@app.on_event("startup")
def startup():
    # 1) backfill all categories
    category_tagger.retag_all()
    # 2) watch for document‐stream updates
    threading.Thread(target=category_tagger.watch_changes, daemon=True).start()
    # 3) watch for notifications to dispatch
    threading.Thread(target=notifications.watch_and_process, daemon=True).start()
