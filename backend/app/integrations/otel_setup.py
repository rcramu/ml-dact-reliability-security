"""OpenTelemetry tracing setup (req.md Sec. 38)."""
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ..config import settings

logger = logging.getLogger("churnplatform.otel")


def configure_otel(app) -> None:
    try:
        resource = Resource(attributes={SERVICE_NAME: settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry configured -> %s", settings.otel_exporter_otlp_endpoint)
    except Exception:  # pragma: no cover - tracing must never break serving
        logger.warning("OpenTelemetry setup failed; continuing without tracing", exc_info=True)


def get_tracer():
    return trace.get_tracer(settings.otel_service_name)
