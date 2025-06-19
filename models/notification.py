from pydantic import BaseModel, Field, ConfigDict
from typing import Any
from datetime import datetime
from bson import ObjectId

# Using the same PyObjectId from user.py (Pydantic v2 compatible)
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

class Notification(BaseModel):
    model_config = ConfigDict(
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat()},
        populate_by_name=True,
        arbitrary_types_allowed=True
    )
    
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    message: str
    created_at: datetime
    read: bool = False
    sent: bool = False
