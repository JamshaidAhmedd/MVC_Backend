from pydantic import BaseModel
from typing import List

class CategoryIn(BaseModel):
    name: str
    description: str = ""
    keywords: List[str]

class CategoryOut(CategoryIn):
    id: str
