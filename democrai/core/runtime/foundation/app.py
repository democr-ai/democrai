from dataclasses import dataclass
from contextlib import contextmanager
from typing import Optional
import contextvars
import threading

from democrai.core.platform.utils.identity import to_optional_int

"""
Singleton application main
"""


class AppContext:
    """
    Singleton container for global application services and state.

    AppContext holds references to core services like the logger, network,
    router, database session factory, and module manager. It is initialized
    once at startup.
    """

    _instance: "AppContext | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "AppContext":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._do_init()
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        # init is handled in __new__ under lock; nothing to do here
        pass

    def _do_init(self) -> None:
        self.logger = None
        self.network = None
        self.router = None
        self.config = None
        self.db = None
        self.media = None
        self.data_store = None
        self.kg_store = None
        self.obs_store = None
        self.obs_maintenance_service = None
        self.vector_store = None
        self.knowledge_service = None
        self.knowledge_ingestion = None
        self.knowledge_runtime = None
        self.setup_mode = False
        self.dev = False
        self.runtime_mode = None
        self.runtime_module_paths = ()
        self.runtime_engine_paths = ()
        self.runtime_extractor_paths = ()
        self.node_id = None
        self.engine_orchestrator_process = None
        self.knowledge_query_process = None
        self.knowledge_query_stop_event = None
        self.knowledge_query_future = None
        self.runtime_prompt_grpc_server = None
        self.runtime_prompt_grpc_future = None
        self.engine_install_consumer = None
        self.engine_install_worker_process = None
        self.engine_runtime = None
        self.extractor_install_consumer = None
        self.extractor_runtime = None
        self.runtime_metrics_publisher = None
        self.knowledge_extraction_worker_process = None
        self.setup_finalize_consumer = None
        self.module_runtime = None
        self.os_network_allowlist = None
        self.os_network_allowlist_active = False
        self.os_sandbox_helper_process = None

        from democrai.core.infrastructure.modules.manager import module_manager

        self.modules = module_manager

        self.task_manager = None  # Initialized by Network
        self.connection_registry = None  # Initialized by Network
        self.redis_task_bridge = None  # Initialized by Network (if Redis enabled)
        self.request_flow_tracer = None

        from democrai.core.runtime.observability.action_locks import ActionLockManager

        self.action_lock_manager = ActionLockManager()

        from democrai.core.runtime.foundation.di import Container

        self.container = Container()


def app_ctx() -> AppContext:
    """
    Global accessor for the singleton AppContext instance.

    :return: The active AppContext.
    """
    return AppContext()


def module_name_from_action(action_name: str | None) -> str:
    name = action_name if isinstance(action_name, str) else ""
    return name.split(".", 1)[0] if "." in name else "core"


@dataclass
class RequestContext:
    """
    Thread-local or task-local context for a single request.

    Stores information about the current user, organization, access level,
    and the communication channel (HTTP/WS/IPC).
    """

    request_id: str
    user: Optional[int]
    role: Optional[str]  # Added for auth
    organization_id: Optional[int]
    access_level: Optional[int]
    channel: str  # "http" | "ws" | "ipc"
    app: Optional[AppContext] = None
    session_key: Optional[str] = None
    client_ip: Optional[str] = None
    action_name: Optional[str] = None
    module_name: str = "core"
    stream_id: Optional[str] = None


_current_req: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "request_ctx"
)


def set_req_ctx(ctx: RequestContext):
    _debug_request_context("set", ctx)
    return _current_req.set(ctx)


def reset_req_ctx(token) -> None:
    _current_req.reset(token)


def req_ctx() -> RequestContext:
    """
    Accessor for the current request context.

    :return: The RequestContext for the current execution flow.
    :raises LookupError: If no request context is active.
    """
    return _current_req.get()


def request_context_to_dict(ctx: RequestContext | None) -> dict:
    if ctx is None:
        return {}
    return {
        "request_id": ctx.request_id,
        "user": ctx.user,
        "role": ctx.role,
        "organization_id": ctx.organization_id,
        "access_level": ctx.access_level,
        "channel": ctx.channel,
        "session_key": ctx.session_key,
        "client_ip": ctx.client_ip,
        "action_name": ctx.action_name,
        "module_name": ctx.module_name,
        "stream_id": ctx.stream_id,
    }


def _masked_session_key(value: str | None) -> str:
    resolved = value.strip() if isinstance(value, str) else ""
    if not resolved:
        return ""
    if len(resolved) <= 8:
        return "*" * len(resolved)
    return f"{resolved[:4]}...{resolved[-4:]}"


def _debug_request_context(event: str, ctx: RequestContext | None, **fields) -> None:
    from democrai.core.platform.utils.debug import debug_request_context_flow

    debug_request_context_flow(
        event,
        request_id=(
            getattr(ctx, "request_id")
            if ctx is not None and isinstance(getattr(ctx, "request_id", None), str)
            else ""
        ),
        user=getattr(ctx, "user", None),
        organization_id=getattr(ctx, "organization_id", None),
        channel=(
            getattr(ctx, "channel")
            if ctx is not None and isinstance(getattr(ctx, "channel", None), str)
            else ""
        ),
        action_name=getattr(ctx, "action_name", None),
        module_name=(
            getattr(ctx, "module_name")
            if ctx is not None and isinstance(getattr(ctx, "module_name", None), str)
            else ""
        ),
        stream_id=getattr(ctx, "stream_id", None),
        has_session_key=bool(_masked_session_key(getattr(ctx, "session_key", None))),
        session_key=_masked_session_key(getattr(ctx, "session_key", None)),
        **fields,
    )


def request_context_from_dict(payload: dict | None) -> RequestContext | None:
    if not isinstance(payload, dict) or not payload:
        _debug_request_context("from_dict.empty", None)
        return None
    raw_request_id = payload.get("request_id")
    raw_channel = payload.get("channel")
    raw_module_name = payload.get("module_name")
    ctx = RequestContext(
        request_id=raw_request_id if isinstance(raw_request_id, str) else "",
        user=to_optional_int(payload.get("user")),
        role=payload.get("role"),
        organization_id=to_optional_int(payload.get("organization_id")),
        access_level=to_optional_int(payload.get("access_level")),
        channel=raw_channel if isinstance(raw_channel, str) and raw_channel else "ipc",
        app=app_ctx(),
        session_key=payload.get("session_key"),
        client_ip=payload.get("client_ip"),
        action_name=payload.get("action_name"),
        module_name=(
            raw_module_name
            if isinstance(raw_module_name, str) and raw_module_name
            else "core"
        ),
        stream_id=payload.get("stream_id"),
    )
    _debug_request_context("from_dict.created", ctx)
    return ctx


def current_request_context_payload(origin: str | None = None) -> dict:
    try:
        ctx = req_ctx()
        _debug_request_context(
            "payload.captured",
            ctx,
            **({"origin": origin} if isinstance(origin, str) and origin else {}),
        )
        return request_context_to_dict(ctx)
    except LookupError:
        _debug_request_context(
            "payload.missing",
            None,
            **({"origin": origin} if isinstance(origin, str) and origin else {}),
        )
        return {}


@contextmanager
def request_context_scope(payload: dict | None):
    ctx = request_context_from_dict(payload)
    if ctx is None:
        _debug_request_context("scope.empty", None)
        yield
        return
    _debug_request_context("scope.enter", ctx)
    token = set_req_ctx(ctx)
    try:
        yield
    finally:
        reset_req_ctx(token)
        _debug_request_context("scope.exit", ctx)
