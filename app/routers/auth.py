from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.core import security
from app.core.config import db
from app.models.user import UserCreate, UserOut, Token

router = APIRouter(prefix="/users", tags=["auth"])

@router.post("/register", response_model=UserOut, status_code=201)
def register(user: UserCreate):
    # Ensure unique username and email
    if db["users"].find_one({"username": user.username}) or db["users"].find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Username or email already registered")
    # Hash the password and construct the user document
    hashed_pw = security.get_password_hash(user.password)
    doc = {
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "hashed_password": hashed_pw,
        "is_active": True,
        "is_admin": False,
        "favorites": [],
        "notifications": []
    }
    result = db["users"].insert_one(doc)
    # Fetch the inserted user and return as UserOut
    new_user = db["users"].find_one({"_id": result.inserted_id})
    return UserOut(**new_user, id=str(result.inserted_id))

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Verify user credentials
    user_doc = db["users"].find_one({"username": form_data.username})
    if not user_doc or not security.verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    # Create JWT token with user info
    access_token = security.create_access_token(
        {"sub": user_doc["username"], "user_id": str(user_doc["_id"])}
    )
    return {"access_token": access_token, "token_type": "bearer"}
