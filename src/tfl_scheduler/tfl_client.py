"""
Transport for London (TfL) Unified API HTTP client and provider abstractions.

Defines a small structural `Protocol` so the scheduler depends on an interface,
not on `requests` directly—this makes tests inject fakes without subclassing.
`TflClient` performs GET `/Line/{ids}/Disruption`, validates HTTP status, JSON shape,
and translates `requests` exceptions into `ProviderError` subclasses for consistent
repository handling.
"""
from typing import Protocol  # Structural subtyping: implementations match methods without explicit inheritance
import requests  # Third-party HTTP library used synchronously from scheduler thread


class DisruptionProvider(Protocol):  # Implementors only need `get_disruptions`; no inheritance required at runtime
    def get_disruptions(self, lines: list[str]) -> list[dict]:  # Method signature enforced by type checkers
        pass  # Protocol bodies are ignored at runtime; `...` could also be used


class ProviderError(Exception):  # Base class for all provider failures caught by scheduler
    pass


class ProviderTimeout(ProviderError):  # Specific classification for read timeouts
    pass


class ProviderBadResponse(ProviderError):  # HTTP OK but body not usable JSON list of objects
    pass


class TflClient:  # Concrete TfL REST implementation
    def __init__(self, base_url: str, timeout_seconds: float):  # Configures root URL and per-request timeout
        self._base_url = base_url.rstrip("/")  # Avoid double slashes when interpolating paths
        self._timeout_seconds = timeout_seconds  # Passed to `requests.get` to cap blocking time

    def get_disruptions(self, lines: list[str]) -> list[dict]:  # Public API consumed by `TaskScheduler.run_task`
        line_ids = ",".join(lines)  # TfL expects comma-separated line ids in the path segment
        url = f"{self._base_url}/Line/{line_ids}/Disruption"  # Official endpoint pattern for disruption feed

        try:  # Separate network errors from parse errors
            response = requests.get(url, timeout=self._timeout_seconds)  # Blocking GET
            response.raise_for_status()  # Turn 4xx/5xx into `requests.HTTPError`
        except requests.Timeout as exc:  # Explicit timeout classification
            raise ProviderTimeout("Provider timed out before returning a result.") from exc
        except requests.RequestException as exc:  # Broad bucket for connection errors, HTTP errors, etc.
            raise ProviderError(f"Provider request failed: {exc}") from exc

        try:
            payload = response.json()  # Parse JSON body
        except ValueError as exc:  # `json()` raises ValueError on invalid JSON
            raise ProviderBadResponse("Provider returned invalid JSON.") from exc

        if not isinstance(payload, list):  # Contract expects top-level JSON array
            raise ProviderBadResponse("Provider response must be a list.")
        if not all(isinstance(item, dict) for item in payload):  # Each disruption entry should be an object
            raise ProviderBadResponse("Provider response items must be objects.")

        return payload  # Pass through raw dicts; repository stores them as JSON
