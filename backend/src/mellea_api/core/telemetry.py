"""OpenTelemetry configuration for observability."""

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

if TYPE_CHECKING:
    from fastapi import FastAPI

from mellea_api.core.config import Settings

logger = logging.getLogger(__name__)


def setup_telemetry(app: "FastAPI", settings: Settings) -> None:
    """Configure OpenTelemetry tracing for the application.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled")
        return

    # Create resource with service info
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add exporters based on environment
    if settings.environment == "development":
        # Console exporter for development (only if debug)
        if settings.debug:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # OTLP exporter for staging/production
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except Exception as e:
            logger.warning(f"Failed to configure OTLP exporter: {e}")

    # Set the tracer provider
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    logger.info(
        f"OpenTelemetry configured: service={settings.otel_service_name}, "
        f"environment={settings.environment}"
    )


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)
