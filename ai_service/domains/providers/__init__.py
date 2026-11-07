"""Explicit model-provider selection for the existing AI service.

Gemini remains the default. ``opencode_cli`` is an opt-in per-run model
transport; tool/planner/validator authority stays in the AI service.
"""

from .aibox_provider import AdapterError, AiboxHttpProvider
from .config import (DEFAULT_AIBOX_MODEL, DEFAULT_CLI_MODEL, MODEL_DISPLAY_NAME,
                     MODEL_UPSTREAM_NOTE, MODEL_UPSTREAM_VERSION_VERIFIED,
                     PROVIDER_AIBOX, PROVIDER_AIBOX_HTTP, PROVIDER_GEMINI,
                     PROVIDER_OPENCODE_CLI, ProviderConfig,
                     load_provider_config)
from .errors import ModelUnavailableError, ProviderConfigError, ProviderError
from . import cli_runtime
from .opencode_cli import (CliCapabilities, OpenCodeCliProvider,
                           build_export_argv, build_prompt, build_run_argv,
                           capabilities_for, convert_assistant_output,
                           openai_usage, probe_cli_capabilities,
                           reset_capability_cache)

__all__ = [
    "AdapterError",
    "AiboxHttpProvider",
    "DEFAULT_AIBOX_MODEL",
    "DEFAULT_CLI_MODEL",
    "MODEL_DISPLAY_NAME",
    "MODEL_UPSTREAM_NOTE",
    "MODEL_UPSTREAM_VERSION_VERIFIED",
    "PROVIDER_AIBOX",
    "PROVIDER_AIBOX_HTTP",
    "PROVIDER_GEMINI",
    "PROVIDER_OPENCODE_CLI",
    "ProviderConfig",
    "ProviderConfigError",
    "ProviderError",
    "ModelUnavailableError",
    "CliCapabilities",
    "OpenCodeCliProvider",
    "cli_runtime",
    "load_provider_config",
    "build_export_argv",
    "build_prompt",
    "build_run_argv",
    "capabilities_for",
    "convert_assistant_output",
    "openai_usage",
    "probe_cli_capabilities",
    "reset_capability_cache",
]
