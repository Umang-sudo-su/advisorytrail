from pydantic import BaseModel, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

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
    findings: List[FindingResponse] = []
    model_config = ConfigDict(from_attributes=True)