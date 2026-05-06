from typing import Protocol

import requests


class DisruptionProvider(Protocol):
    def get_disruptions(self, lines: list[str]) -> list[dict]:
        pass


class ProviderError(Exception):
    """Raised when the external data or model provider cannot return a result."""


class ProviderTimeout(ProviderError):
    pass


class ProviderBadResponse(ProviderError):
    pass


class TflClient:
    def __init__(self, base_url: str, timeout_seconds: float):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_disruptions(self, lines: list[str]) -> list[dict]:
        line_ids = ",".join(lines)
        url = f"{self._base_url}/Line/{line_ids}/Disruption"

        try:
            response = requests.get(url, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderTimeout("Provider timed out before returning a result.") from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderBadResponse("Provider returned invalid JSON.") from exc

        if not isinstance(payload, list):
            raise ProviderBadResponse("Provider response must be a list.")
        if not all(isinstance(item, dict) for item in payload):
            raise ProviderBadResponse("Provider response items must be objects.")

        return payload
