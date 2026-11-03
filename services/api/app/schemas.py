from pydantic import BaseModel, EmailStr
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from datetime import datetime
from app.models import ScanStatus



class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True

# --- FINDINGS ---
class FindingBase(BaseModel):
    osv_id: str
    package_name: str
    package_version: str
    severity: str
    details: Optional[Any] = None

class FindingResponse(FindingBase):
    id: int
    scan_id: int
    model_config = ConfigDict(from_attributes=True)

# --- SCANS ---
class ScanBase(BaseModel):
    commit_hash: str
    status: ScanStatus = ScanStatus.PENDING

class ScanResponse(ScanBase):
    id: int
    repository_id: int
    created_at: datetime
    findings: List[FindingResponse] = []
    model_config = ConfigDict(from_attributes=True)

# --- REPOSITORIES ---
class RepositoryBase(BaseModel):
    github_id: str
    name: str
    url: str

class RepositoryResponse(RepositoryBase):
    id: int
    scans: List[ScanResponse] = []
    model_config = ConfigDict(from_attributes=True)

from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True
