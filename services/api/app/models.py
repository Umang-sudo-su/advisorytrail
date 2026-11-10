from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from app.database import Base

class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    scans = relationship("Scan", back_populates="repository", cascade="all, delete-orphan")

class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    commit_hash = Column(String, nullable=False)
    status = Column(String, default=ScanStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    repository = relationship("Repository", back_populates="scans")
    findings = relationship("Finding", back_populates="scan", cascade="all, delete-orphan")
    base_commit_hash = Column(String, nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def duration_seconds(self):
        """Real elapsed time of the scan, or None when it never finished."""
        if not self.created_at:
            return None

        end = self.finished_at
        if end is None:
            if self.status not in {ScanStatus.PENDING.value, ScanStatus.IN_PROGRESS.value}:
                return None
            end = datetime.now(timezone.utc)

        start = self.created_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        return round(max((end - start).total_seconds(), 0.0), 1)

class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    osv_id = Column(String, nullable=False)
    package_name = Column(String, nullable=False)
    package_version = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    details = Column(JSON, nullable=True)

    scan = relationship("Scan", back_populates="findings")
    
    status = Column(String, default="OPEN") 

class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"))
    rule_type = Column(String, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String, nullable=False)           # e.g., umang@buildshield.dev
    action = Column(String, nullable=False)          # e.g., FINDING_DISMISSED, WEBHOOK_DELIVERY_DEDUPLICATED
    resource_id = Column(String, nullable=False)     # e.g., vuln-998122
    justification = Column(String, nullable=True)    # e.g., False positive identification
    category = Column(String, nullable=False)        # e.g., Finding Reviews, Webhooks, Policies, Tenant Access