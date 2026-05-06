from unittest.mock import Mock, patch

import pytest
import requests

from tfl_scheduler.tfl_client import ProviderBadResponse, ProviderError, ProviderTimeout, TflClient


def test_tfl_client_returns_disruptions():
    response = Mock()
    response.json.return_value = [{"description": "Minor delays"}]
    response.raise_for_status.return_value = None

    with patch("tfl_scheduler.tfl_client.requests.get", return_value=response) as get:
        result = TflClient("https://api.tfl.gov.uk", 5).get_disruptions(["victoria"])

    get.assert_called_once_with(
        "https://api.tfl.gov.uk/Line/victoria/Disruption",
        timeout=5,
    )
    assert result == [{"description": "Minor delays"}]


def test_tfl_client_allows_empty_disruption_list():
    response = Mock()
    response.json.return_value = []
    response.raise_for_status.return_value = None

    with patch("tfl_scheduler.tfl_client.requests.get", return_value=response):
        result = TflClient("https://api.tfl.gov.uk", 5).get_disruptions(["victoria"])

    assert result == []


def test_tfl_client_wraps_timeout():
    with patch(
        "tfl_scheduler.tfl_client.requests.get",
        side_effect=requests.Timeout("slow"),
    ):
        with pytest.raises(ProviderTimeout):
            TflClient("https://api.tfl.gov.uk", 5).get_disruptions(["victoria"])


def test_tfl_client_wraps_http_error():
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("500")

    with patch("tfl_scheduler.tfl_client.requests.get", return_value=response):
        with pytest.raises(ProviderError):
            TflClient("https://api.tfl.gov.uk", 5).get_disruptions(["victoria"])


def test_tfl_client_rejects_malformed_response():
    response = Mock()
    response.json.return_value = {"not": "a list"}
    response.raise_for_status.return_value = None

    with patch("tfl_scheduler.tfl_client.requests.get", return_value=response):
        with pytest.raises(ProviderBadResponse):
            TflClient("https://api.tfl.gov.uk", 5).get_disruptions(["victoria"])
