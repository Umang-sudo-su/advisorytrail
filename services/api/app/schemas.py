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
    # Plain text on the way out: internal accounts may use reserved domains such as
    # ".local", which EmailStr rejects. Registration still validates input strictly.
    email: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class RepositoryCreate(BaseModel):
    # `name` is optional: the server resolves the canonical owner/name from GitHub.
    name: Optional[str] = Field(default=None, max_length=200)
    url: str = Field(min_length=3, max_length=300)
    branch: Optional[str] = Field(default=None, max_length=250)

class RepositoryResponse(BaseModel):
    id: int
    name: str
    url: str
    branch: str = "main"
    private: bool = False
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class FindingResponse(BaseModel):
    id: int
    scan_id: int
    osv_id: str
    package_name: str
    package_version: str
    severity: str
    # Review state: OPEN, DISMISSED or FALSE_POSITIVE.
    status: str = "OPEN"
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
    findings_count: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)