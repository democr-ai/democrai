from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.observability.exporters.base import ObsExporter


class OtlpObsExporter(ObsExporter):
    """OTLP trace exporter that mirrors stored events as spans."""

    def __init__(
        self,
        endpoint: str,
        *,
        insecure: bool = False,
        service_name: str = "democrai",
    ):
        if not endpoint:
            raise ValueError("OTLP exporter requires endpoint")
        self._span_context_manager = self._build_exporter(
            endpoint=endpoint,
            insecure=insecure,
            service_name=service_name,
        )

    @staticmethod
    def _build_exporter(
        *, endpoint: str, insecure: bool, service_name: str
    ) -> Any:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise ProviderNotAvailableError(
                "OTLP observability exporter requires opentelemetry-sdk and opentelemetry-exporter-otlp"
            ) from exc

        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
            )
        )
        tracer = provider.get_tracer("democrai.observability")
        return tracer.start_as_current_span

    def export(self, event_payload: dict) -> None:
        span_name = f"{event_payload.get('category', 'system')}.{event_payload.get('event', 'event')}"
        duration_ms = event_payload.get("duration_ms")
        ctx = (
            self._span_context_manager(span_name)
            if duration_ms is None
            else self._span_context_manager(span_name)
        )
        with ctx if ctx is not None else nullcontext() as span:
            if span is None:
                return
            span.set_attribute("democrai.level", str(event_payload.get("level", "INFO")))
            span.set_attribute(
                "democrai.correlation_id",
                str(event_payload.get("correlation_id", "")),
            )
            for key in ("user_id", "session_id", "agent_id", "category"):
                value = event_payload.get(key)
                if value is not None:
                    span.set_attribute(f"democrai.{key}", str(value))
            payload = event_payload.get("payload")
            if isinstance(payload, dict):
                for key, value in payload.items():
                    if isinstance(value, (str, bool, int, float)):
                        span.set_attribute(f"democrai.payload.{key}", value)
