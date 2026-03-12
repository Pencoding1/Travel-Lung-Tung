from pydantic import BaseModel, Field

class BaseEntity(BaseModel):
    id: str=Field(alias="ID")
