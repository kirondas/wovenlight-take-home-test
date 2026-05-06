from typing import Any

import requests


class TflClientError(RuntimeError):
    """Raised when TfL cannot return disruption data for a scheduled task."""


class TflClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_line_disruptions(self, lines: tuple[str, ...]) -> list[dict[str, Any]]:
        line_path = ",".join(lines)
        url = f"{self.base_url}/Line/{line_path}/Disruption"

        try:
            response = requests.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TflClientError(f"TfL request failed for lines '{line_path}': {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TflClientError("TfL returned a non-JSON response") from exc

        if not isinstance(payload, list):
            raise TflClientError("TfL disruption response did not match the expected list shape")

        return payload
