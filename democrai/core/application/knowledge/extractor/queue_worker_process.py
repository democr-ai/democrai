"""Standalone process entrypoint for the knowledge extraction queue."""

from __future__ import annotations

import signal
import threading
import time

from democrai.core.infrastructure.observability.logger.manager import LoggerManager
from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
from democrai.core.infrastructure.storage.media.factory import MediaProviderFactory
from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import configure_temp_environment, logs_dir

from .queue_processor import build_default_extraction_queue_processor


_STOP_EVENT = threading.Event()


def _request_stop(_signum, _frame) -> None:
    _STOP_EVENT.set()


def _bootstrap_context() -> None:
    ctx = app_ctx()
    configure_temp_environment()
    ctx.logger = LoggerManager(log_dir=str(logs_dir()))
    bootstrapper = RuntimeBootstrapper()
    bootstrapper.init_config(ctx)
    if getattr(ctx, "setup_mode", False):
        raise RuntimeError("knowledge_extraction_worker_setup_mode")
    _init_queue_storage(ctx)


def _init_queue_storage(ctx) -> None:
    config = ctx.config
    db_type = config.get("database.type", "sqlite")
    db_url = config.get("database.url", None)

    media_type = config.get("storage.media.type", "local")
    media_path = config.get("storage.media.path", None)
    media_bucket = config.get("storage.media.bucket")
    media_region = config.get("storage.media.region", "us-east-1")
    media_access_key = config.get("storage.media.access_key")
    media_secret_key = config.get("storage.media.secret_key")
    media_session_token = config.get("storage.media.session_token")
    media_endpoint_url = config.get("storage.media.endpoint_url")
    media_public_base_url = config.get("storage.media.public_base_url")
    media_key_prefix = config.get("storage.media.key_prefix")
    media_use_path_style = config.get("storage.media.use_path_style", False)

    logger = getattr(ctx, "logger", None)
    if logger is not None:
        logger.info(
            f"[Bootstrap] Initializing extraction queue providers: db={db_type}, media={media_type}"
        )

    ctx.db = PersistenceProviderFactory.get_provider(db_type, db_url=db_url)
    ctx.media = MediaProviderFactory.get_provider(
        media_type,
        base_dir=media_path,
        bucket_name=media_bucket,
        region=media_region,
        access_key=media_access_key,
        secret_key=media_secret_key,
        session_token=media_session_token,
        endpoint_url=media_endpoint_url,
        public_base_url=media_public_base_url,
        key_prefix=media_key_prefix,
        use_path_style=media_use_path_style,
    )


def run_worker_loop(*, batch_size: int, poll_seconds: float) -> int:
    _bootstrap_context()
    processor = build_default_extraction_queue_processor()
    sleep_seconds = max(0.1, float(poll_seconds or 2.0))
    while not _STOP_EVENT.is_set():
        stats = processor.process_batch(batch_size=max(1, int(batch_size or 1)))
        if stats.claimed == 0:
            _STOP_EVENT.wait(sleep_seconds)
            continue
        time.sleep(0)
    return 0


def main() -> int:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_stop)
    return run_worker_loop(batch_size=1, poll_seconds=2.0)


if __name__ == "__main__":
    raise SystemExit(main())
