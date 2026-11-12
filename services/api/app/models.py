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
    # Authenticator-app 2FA. The secret is stored encrypted; recovery codes are hashed.
    two_factor_secret = Column(String, nullable=True)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    two_factor_recovery = Column(JSON, nullable=True)
    # Bumped to invalidate every previously issued token for this account.
    token_version = Column(Integer, default=0, nullable=False)

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    # Full GitHub slug, e.g. "octocat/Hello-World"; scans and webhooks rely on it.
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    branch = Column(String, nullable=False, default="main")
    is_private = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    scans = relationship("Scan", back_populates="repository", cascade="all, delete-orphan")

class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False, index=True)
    commit_hash = Column(String, nullable=False)
    status = Column(String, default=ScanStatus.PENDING.value, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

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
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, index=True)
    osv_id = Column(String, nullable=False)
    package_name = Column(String, nullable=False)
    package_version = Column(String, nullable=False)
    severity = Column(String, nullable=False, index=True)
    details = Column(JSON, nullable=True)

    scan = relationship("Scan", back_populates="findings")
    
    status = Column(String, default="OPEN", index=True) 

class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"))
    rule_type = Column(String, nullable=False)

class PolicySettings(Base):
    """Single org-wide policy configuration edited on the Policies page."""
    __tablename__ = "policy_settings"

    id = Column(Integer, primary_key=True)
    mode = Column(String, nullable=False, default="enforce")
    rules = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class WorkspaceSettings(Base):
    """Single row holding org-wide Settings values (workspace + scan defaults)."""
    __tablename__ = "workspace_settings"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="AdvisoryTrail")
    settings = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserPreference(Base):
    """Per-user Settings preferences, kept apart from workspace-wide defaults."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    settings = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False, default="developer")
    status = Column(String, nullable=False, default="pending")
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ApiToken(Base):
    """Hashed programmatic credential. The secret itself is shown once, never stored."""
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    scopes = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    events = Column(JSON, nullable=False, default=list)
    secret = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)
    last_delivery_status = Column(String, nullable=True)


class Session(Base):
    """One signed-in device. JWTs carry the session ``jti`` so a session can be revoked."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    jti = Column(String, unique=True, index=True, nullable=False)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class IntegrationCredential(Base):
    """Sealed third-party credential, e.g. the GitHub token connected from Settings."""
    __tablename__ = "integration_credentials"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, unique=True, nullable=False)
    sealed_token = Column(String, nullable=False)
    account = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Notification(Base):
    """Queued notification. Immediate ones are sent at once; digests wait for the scheduler."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(String, nullable=False)
    digest = Column(String, nullable=False, default="immediate")
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="queued")
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String, nullable=False)           # e.g., umang@advisorytrail.dev
    action = Column(String, nullable=False)          # e.g., FINDING_DISMISSED, WEBHOOK_DELIVERY_DEDUPLICATED
    resource_id = Column(String, nullable=False)     # e.g., vuln-998122
    justification = Column(String, nullable=True)    # e.g., False positive identification
    category = Column(String, nullable=False, index=True)        # e.g., Finding Reviews, Webhooks, Policies, Tenant Access