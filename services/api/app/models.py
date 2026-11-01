import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Repository(Base):
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    url = Column(String)
    
    scans = relationship("Scan", back_populates="repository", cascade="all, delete-orphan")

class Scan(Base):
    __tablename__ = "scans"
    
    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    commit_hash = Column(String, index=True)
    status = Column(Enum(ScanStatus), default=ScanStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    repository = relationship("Repository", back_populates="scans")
    findings = relationship("Finding", back_populates="scan", cascade="all, delete-orphan")

class Finding(Base):
    __tablename__ = "findings"
    
    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"))
    osv_id = Column(String, index=True)
    package_name = Column(String)
    package_version = Column(String)
    severity = Column(String)
    details = Column(JSON) 
    
    scan = relationship("Scan", back_populates="findings")

from sqlalchemy import Boolean, DateTime
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
