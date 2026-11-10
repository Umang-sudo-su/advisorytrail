from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class RepositoryCreate(BaseModel):
    name: str
    url: str

class RepositoryResponse(BaseModel):
    id: int
    name: str
    url: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class FindingResponse(BaseModel):
    id: int
    scan_id: int
    osv_id: str
    package_name: str
    package_version: str
    severity: str
    details: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)

class ScanCreate(BaseModel):
    repository_id: int
    commit_hash: str

class ScanResponse(BaseModel):
    id: int
    repository_id: int
    commit_hash: str
    status: str
    created_at: datetime
    duration_seconds: Optional[float] = None
    findings: List[FindingResponse] = []
    model_config = ConfigDict(from_attributes=True)