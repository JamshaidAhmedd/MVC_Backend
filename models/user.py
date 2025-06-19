from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from bson import ObjectId
from datetime import datetime

# Custom PyObjectId type for MongoDB ObjectId handling (Pydantic v2 compatible)
class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler):
        from pydantic_core import core_schema
        return core_schema.with_info_before_validator_function(
            cls.validate,
            core_schema.str_schema(),
        )

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, handler):
        field_schema.update(type="string")
        return field_schema

class UserBase(BaseModel):
    username: str
    email: str
    full_name: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None

class UserInDB(UserBase):
    model_config = ConfigDict(
        json_encoders={ObjectId: str},
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    is_active: bool = True
    is_admin: bool = False
    favorites: List[str] = []
    notifications: List[dict] = []

class UserOut(UserBase):
    model_config = ConfigDict(
        json_encoders={ObjectId: str},
        populate_by_name=True
    )
    
    id: str
    is_active: bool
    is_admin: bool
    favorites: List[str]
    notifications: List[dict]

class FavoriteIn(BaseModel):
    course_id: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None
    is_admin: bool = False
