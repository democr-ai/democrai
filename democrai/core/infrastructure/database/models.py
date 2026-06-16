from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    Index,
    JSON,
    ForeignKey,
    Table,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from democrai.core.platform.utils.timezone import utc_now_naive


class Base(DeclarativeBase):
    pass


# Association tables
con_user_role = Table(
    "con_user_role",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)

con_role_permission = Table(
    "con_role_permission",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)  # Static for now as per user req
    language = Column(String(10), nullable=True, default="en")
    access_level = Column(Integer, nullable=False, default=3, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)

    organization = relationship("Organization", back_populates="users")
    roles = relationship("Role", secondary=con_user_role, back_populates="users")

    def __repr__(self):
        return f"<User(username='{self.username}')>"


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    users = relationship("User", secondary=con_user_role, back_populates="roles")
    permissions = relationship(
        "Permission", secondary=con_role_permission, back_populates="roles"
    )

    def __repr__(self):
        return f"<Role(name='{self.name}')>"


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    roles = relationship(
        "Role", secondary=con_role_permission, back_populates="permissions"
    )

    def __repr__(self):
        return f"<Permission(name='{self.name}')>"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)

    users = relationship("User", back_populates="organization")

    def __repr__(self):
        return f"<Organization(name='{self.name}')>"


class OrganizationAgent(Base):
    __tablename__ = "organization_agent"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "agent_name",
            name="uq_organization_agent_organization_agent",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    agent_name = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    organization = relationship("Organization")

    def __repr__(self):
        return (
            f"<OrganizationAgent(organization_id='{self.organization_id}', "
            f"agent_name='{self.agent_name}')>"
        )


class OrganizationMcp(Base):
    __tablename__ = "organization_mcp"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "mcp_server_id",
            name="uq_organization_mcp_organization_server",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    mcp_server_id = Column(Integer, ForeignKey("mcp_server_registry.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    organization = relationship("Organization")
    mcp_server = relationship("McpServerRegistry")

    def __repr__(self):
        return (
            f"<OrganizationMcp(organization_id='{self.organization_id}', "
            f"mcp_server_id='{self.mcp_server_id}')>"
        )


class OrganizationTool(Base):
    __tablename__ = "organization_tool"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "tool_name",
            name="uq_organization_tool_organization_tool",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    organization = relationship("Organization")

    def __repr__(self):
        return (
            f"<OrganizationTool(organization_id='{self.organization_id}', "
            f"tool_name='{self.tool_name}')>"
        )


class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Preference(key='{self.key}', value='{self.value}')>"


class ExternalAccessRequest(Base):
    __tablename__ = "external_access_requests"
    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_name",
            "resource_type",
            "operation",
            "normalized_target",
            "requested_by",
            "session_key",
            name="uq_external_access_request_per_user_session",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_type = Column(String(32), nullable=False, default="module", index=True)
    subject_name = Column(String(255), nullable=False, default="", index=True)
    resource_type = Column(String(32), nullable=False, index=True)
    operation = Column(String(32), nullable=False, default="", index=True)
    target = Column(Text, nullable=False)
    normalized_target = Column(Text, nullable=False, default="")
    scope = Column(String(32), nullable=False, default="pending", index=True)
    requested_by = Column(Integer, nullable=True, index=True)
    subject_chain = Column(JSON, nullable=True)
    session_key = Column(String(512), nullable=True, index=True)
    organization_id = Column(Integer, nullable=True)
    task_id = Column(String(255), nullable=True, index=True)
    resume_action = Column(String(255), nullable=True)
    resume_context = Column(Text, nullable=True)
    resume_context_hash = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    last_requested_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<ExternalAccessRequest(subject='{self.subject_type}:{self.subject_name}', "
            f"operation='{self.operation}', requested_by={self.requested_by}, status='{self.status}')>"
        )


class ExternalAccessApproval(Base):
    __tablename__ = "external_access_approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_type = Column(String(32), nullable=False, default="module", index=True)
    subject_name = Column(String(255), nullable=False, default="", index=True)
    resource_type = Column(String(32), nullable=False, index=True)
    operation = Column(String(32), nullable=False, default="", index=True)
    target = Column(Text, nullable=False)
    normalized_target = Column(Text, nullable=False, default="")
    scope = Column(String(32), nullable=False, default="permanent", index=True)
    session_key = Column(String(512), nullable=True, index=True)
    approved_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<ExternalAccessApproval(subject='{self.subject_type}:{self.subject_name}', "
            f"resource_type='{self.resource_type}', operation='{self.operation}')>"
        )


class MediaUpload(Base):
    __tablename__ = "media_uploads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(64), unique=True, nullable=False, index=True)
    module_name = Column(String(255), nullable=False, index=True)
    storage_path = Column(Text, nullable=False, unique=True)
    original_filename = Column(String(512), nullable=False)
    stored_filename = Column(String(512), nullable=False)
    content_type = Column(String(255), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(128), nullable=False, index=True)
    scope_type = Column(String(32), nullable=False, index=True)
    owner_user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    uploaded_by = Column(Integer, nullable=False, index=True)
    uploader_access_level = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<MediaUpload(file_id='{self.file_id}', module='{self.module_name}', "
            f"owner='{self.owner_user_id}', scope='{self.scope_type}')>"
        )


class EngineRegistry(Base):
    __tablename__ = "engine_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    provider = Column(String(100), nullable=False)  # ollama, llamacpp, openai, etc.
    config = Column(
        JSON, nullable=True, default=dict
    )  # JSON config value, to be encrypted only keys

    status = Column(String(50), default="uninstalled")
    supported = Column(Boolean, default=False)  # True/False

    models = relationship("ModelRegistry", back_populates="engine")

    def __repr__(self):
        return f"<EngineRegistry(name='{self.name}', provider='{self.provider}')>"


class McpServerRegistry(Base):
    __tablename__ = "mcp_server_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    transport = Column(String(16), nullable=False, index=True)
    endpoint_url = Column(Text, nullable=False)
    config_encrypted = Column(Text, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    timeout_ms = Column(Integer, nullable=False, default=15000)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<McpServerRegistry(name='{self.name}', transport='{self.transport}', "
            f"enabled={self.enabled})>"
        )


class EnvironmentVariableRegistry(Base):
    __tablename__ = "environment_variable_registry"
    __table_args__ = (
        UniqueConstraint(
            "subject_kind",
            "subject",
            "name",
            name="uq_environment_variable_registry_subject_name",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_kind = Column(String(50), nullable=False, index=True)
    subject = Column(String(255), nullable=False, default="", index=True)
    name = Column(String(255), nullable=False, index=True)
    value_encrypted = Column(Text, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<EnvironmentVariableRegistry(subject_kind='{self.subject_kind}', "
            f"subject='{self.subject}', name='{self.name}', enabled={self.enabled})>"
        )


class RuntimeNodeRegistry(Base):
    __tablename__ = "runtime_node_registry"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_runtime_node_registry_node_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(255), nullable=False, index=True)
    label = Column(String(255), nullable=False, default="")
    status = Column(String(50), nullable=False, default="active", index=True)
    hostname = Column(String(255), nullable=False, default="")
    has_nvidia_gpu = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    # Written only by the engine orchestrator subprocess node-state publisher;
    # last_seen_at stays owned by the core runtime-metrics writer.
    orchestrator_last_seen_at = Column(DateTime, nullable=True, index=True)
    cpu_percent = Column(Float, nullable=False, default=0.0)
    ram_total_mb = Column(Integer, nullable=False, default=0)
    ram_free_mb = Column(Integer, nullable=False, default=0)
    vram_total_mb = Column(Integer, nullable=False, default=0)
    vram_free_mb = Column(Integer, nullable=False, default=0)
    gpu_inventory_json = Column(Text, nullable=False, default="[]")
    resources_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<RuntimeNodeRegistry(node_id='{self.node_id}', "
            f"status='{self.status}')>"
        )


class EngineNodeInstallRegistry(Base):
    __tablename__ = "engine_node_install_registry"
    __table_args__ = (
        UniqueConstraint(
            "engine_id", "node_id", name="uq_engine_node_install_registry_engine_node"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    engine_id = Column(String(255), nullable=False, index=True)
    node_id = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="pending", index=True)
    last_event_id = Column(String(255), nullable=True, index=True)
    install_started_at = Column(DateTime, nullable=True)
    install_completed_at = Column(DateTime, nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    manifest_version = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    def __repr__(self):
        return (
            f"<EngineNodeInstallRegistry(engine_id='{self.engine_id}', "
            f"node_id='{self.node_id}', status='{self.status}')>"
        )


class EngineNodeInstanceRegistry(Base):
    __tablename__ = "engine_node_instance_registry"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "engine_row_id",
            "model_registry_id",
            name="uq_engine_node_instance_registry_node_engine_model",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(255), nullable=False, index=True)
    engine_row_id = Column(Integer, nullable=False, index=True)
    engine_id = Column(String(255), nullable=False, default="")
    model_registry_id = Column(Integer, nullable=False, index=True)
    model = Column(String(512), nullable=False, default="")
    config_signature = Column(String(128), nullable=False, default="")
    status = Column(String(32), nullable=False, default="running", index=True)
    pid = Column(Integer, nullable=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<EngineNodeInstanceRegistry(node_id='{self.node_id}', "
            f"engine_id='{self.engine_id}', model_registry_id={self.model_registry_id}, "
            f"status='{self.status}')>"
        )


class EngineInvocationQueue(Base):
    __tablename__ = "engine_invocation_queue"
    __table_args__ = (
        Index(
            "ix_engine_invocation_queue_claim",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index(
            "ix_engine_invocation_queue_lease",
            "status",
            "lease_expires_at",
        ),
    )

    # id == request_id: enqueue idempotency through the primary key.
    id = Column(String(64), primary_key=True)
    pipeline_id = Column(String(64), nullable=True)
    selector_type = Column(String(32), nullable=False)
    model_registry_id = Column(Integer, nullable=True)
    objective = Column(String(255), nullable=True)
    capabilities_json = Column(Text, nullable=False, default="[]")
    prefer_local = Column(Boolean, nullable=True)
    confirm_swap = Column(Boolean, nullable=False, default=False)
    method = Column(String(128), nullable=False)
    response_mode = Column(String(16), nullable=False, default="unary")
    payload_json = Column(Text, nullable=False, default="{}")
    request_context_json = Column(Text, nullable=False, default="{}")
    security_context_json = Column(Text, nullable=False, default="{}")
    origin_node_id = Column(String(255), nullable=False, index=True)
    response_stream_key = Column(String(512), nullable=False)
    requires_origin_hitl = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    lease_owner = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    first_chunk_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    result_summary_json = Column(Text, nullable=True)
    claimed_by_node_id = Column(String(255), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<EngineInvocationQueue(id='{self.id}', method='{self.method}', "
            f"status='{self.status}', origin_node_id='{self.origin_node_id}')>"
        )


class ExtractorRegistry(Base):
    __tablename__ = "extractor_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    extractor_id = Column(String(100), nullable=False, index=True)
    config = Column(JSON, nullable=True, default=dict)
    install_config = Column(JSON, nullable=True, default=dict)
    file_extensions = Column(JSON, nullable=False, default=list)
    mime_types = Column(JSON, nullable=False, default=list)
    priority = Column(Integer, nullable=False, default=0)
    status = Column(String(50), default="uninstalled")
    supported = Column(Boolean, default=False)

    def __repr__(self):
        return f"<ExtractorRegistry(name='{self.name}', extractor_id='{self.extractor_id}')>"


class ExtractorMimeTypeBinding(Base):
    __tablename__ = "extractor_mime_type_binding"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mime_type = Column(String(255), unique=True, nullable=False, index=True)
    extractor_id = Column(String(100), nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    def __repr__(self):
        return (
            "<ExtractorMimeTypeBinding("
            f"mime_type='{self.mime_type}', extractor_id='{self.extractor_id}')>"
        )


class ExtractorNodeInstallRegistry(Base):
    __tablename__ = "extractor_node_install_registry"
    __table_args__ = (
        UniqueConstraint(
            "extractor_id", "node_id", name="uq_extractor_node_install_registry_extractor_node"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    extractor_id = Column(String(255), nullable=False, index=True)
    node_id = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="pending", index=True)
    last_event_id = Column(String(255), nullable=True, index=True)
    install_started_at = Column(DateTime, nullable=True)
    install_completed_at = Column(DateTime, nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    manifest_version = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    def __repr__(self):
        return (
            f"<ExtractorNodeInstallRegistry(extractor_id='{self.extractor_id}', "
            f"node_id='{self.node_id}', status='{self.status}')>"
        )


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    # provider = Column(String(100), nullable=False)  # ollama, llamacpp, openai, etc.
    engine_id = Column(Integer, ForeignKey("engine_registry.id"), nullable=False)
    available_model_id = Column(
        Integer, ForeignKey("available_model_registry.id"), nullable=True, index=True
    )
    model_path = Column(String(512), nullable=True)  # local path or identifier

    vram_required_mb = Column(Integer, default=0)
    ram_required_mb = Column(Integer, default=0)

    is_downloaded = Column(Integer, default=0)  # 0=no, 1=yes
    remote_url = Column(String(512), nullable=True)
    version = Column(String(100), nullable=True)

    capabilities = Column(
        Text, nullable=True
    )  # comma-separated: chat,vision,reasoning,general,etc.
    extra_config = Column(JSON, nullable=True)  # capability-specific config, e.g. {"dim": 1536}
    status = Column(String(50), default="available")

    mappings = relationship("ObjectiveMapping", back_populates="model")
    capability_priorities = relationship(
        "ModelCapabilityPriority",
        back_populates="model",
        cascade="all, delete-orphan",
    )
    engine = relationship("EngineRegistry", back_populates="models")
    available_model = relationship(
        "AvailableModelRegistry",
        back_populates="bindings",
    )

    def __repr__(self):
        return f"<ModelRegistry(name='{self.name}', engine='{self.engine}')>"


class AvailableModelRegistry(Base):
    __tablename__ = "available_model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    catalog_model_id = Column(String(255), nullable=True, index=True)
    source_kind = Column(String(50), nullable=False, default="manual")
    provider_hint = Column(String(100), nullable=True, index=True)
    format = Column(String(100), nullable=True, index=True)
    family = Column(String(100), nullable=True)
    summary = Column(Text, nullable=True)
    storage_ref = Column(String(512), nullable=True)
    remote_url = Column(String(512), nullable=True)
    version = Column(String(100), nullable=True)
    capabilities = Column(Text, nullable=True)
    extended_capabilities = Column(Text, nullable=True)
    interfaces = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    requirements = Column(JSON, nullable=True)
    artifacts = Column(JSON, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    source_payload = Column(JSON, nullable=True)
    extra_config = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="available", index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    bindings = relationship("ModelRegistry", back_populates="available_model")

    def __repr__(self):
        return f"<AvailableModelRegistry(name='{self.name}', source_kind='{self.source_kind}')>"


class ObjectiveMapping(Base):
    __tablename__ = "objective_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    objective = Column(
        String(100), unique=True, nullable=False
    )  # chat, vision, tool_calling, etc.
    model_id = Column(Integer, ForeignKey("model_registry.id"), nullable=False)

    model = relationship("ModelRegistry", back_populates="mappings")

    def __repr__(self):
        return f"<ObjectiveMapping(objective='{self.objective}', model_id={self.model_id})>"


class ModelCapabilityPriority(Base):
    __tablename__ = "model_capability_priority"
    __table_args__ = (
        UniqueConstraint("capability", "model_id", name="uq_capability_model_priority"),
        UniqueConstraint("capability", "priority", name="uq_capability_priority_rank"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    capability = Column(String(100), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("model_registry.id"), nullable=False, index=True)
    priority = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    model = relationship("ModelRegistry", back_populates="capability_priorities")

    def __repr__(self):
        return (
            f"<ModelCapabilityPriority(capability='{self.capability}', "
            f"model_id={self.model_id}, priority={self.priority})>"
        )


class KnowledgeRuntimeConfig(Base):
    __tablename__ = "knowledge_runtime_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enabled = Column(Boolean, nullable=False, default=False)
    embedding_model_registry_id = Column(
        Integer, ForeignKey("model_registry.id"), nullable=True, index=True
    )
    rerank_model_registry_id = Column(
        Integer, ForeignKey("model_registry.id"), nullable=True, index=True
    )
    classification_model_registry_id = Column(
        Integer, ForeignKey("model_registry.id"), nullable=True, index=True
    )
    triple_extractor_model_registry_id = Column(
        Integer, ForeignKey("model_registry.id"), nullable=True, index=True
    )
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)

    def __repr__(self):
        return f"<KnowledgeRuntimeConfig(id={self.id}, enabled={self.enabled})>"


class AgentModelConfig(Base):
    __tablename__ = "agent_model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(255), unique=True, nullable=False, index=True)
    model_policy = Column(String(32), nullable=False, default="by_system", index=True)
    model_registry_id = Column(Integer, ForeignKey("model_registry.id"), nullable=True, index=True)
    extra_tools = Column(JSON, nullable=True)
    extra_skills = Column(JSON, nullable=True)
    extra_mcp_servers = Column(JSON, nullable=True)
    extra_agents = Column(JSON, nullable=True)
    max_iterations = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    model = relationship("ModelRegistry")

    def __repr__(self):
        return (
            f"<AgentModelConfig(agent_name='{self.agent_name}', "
            f"model_policy='{self.model_policy}', model_registry_id={self.model_registry_id})>"
        )


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_key = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)  # JSON-serialized session dict
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f"<Session(user_key='{self.user_key}')>"


class SessionIdentity(Base):
    __tablename__ = "session_identities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f"<SessionIdentity(session_key='{self.session_key}')>"


class SessionUiState(Base):
    __tablename__ = "session_ui_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f"<SessionUiState(session_key='{self.session_key}')>"


class ModuleCommandState(Base):
    __tablename__ = "module_command_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_name = Column(String(255), nullable=False, index=True)
    command_name = Column(String(255), unique=True, nullable=False, index=True)
    lifecycle = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="idle", index=True)
    run_count = Column(Integer, nullable=False, default=0)
    last_started_at = Column(DateTime, nullable=True)
    last_finished_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    lease_owner = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<ModuleCommandState(command_name='{self.command_name}', "
            f"status='{self.status}', lease_owner='{self.lease_owner}')>"
        )


class ModuleLock(Base):
    __tablename__ = "module_lock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_name = Column(String(255), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f"<ModuleLock(module_name='{self.module_name}', "


# Register additional core-domain tables on the same metadata for Alembic.
from democrai.core.application.knowledge import records as _knowledge_records  # noqa: F401
from democrai.core.application.tasks import models as _task_models  # noqa: F401
