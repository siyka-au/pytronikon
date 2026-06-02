"""Pytest configuration and shared fixtures."""

import http.client
import io
import os

import pytest


@pytest.fixture
def english_language_map() -> dict[str, str]:
    """Minimal English language map for testing."""
    return {
        "MPL_6994": "Compressor Outlet Pressure",
        "MPL_6995": "Compressor Inlet Pressure",
        "MPL_7000": "Motor Current",
        "MSTATE_0": "Stopped",
        "MSTATE_1": "Running",
        "MSTATE_2": "Fault",
    }


class FakeResponse:
    """A fake HTTP response for testing."""

    def __init__(self, status: int = 200, reason: str = "OK", body: bytes = b""):
        self.status = status
        self.reason = reason
        self.body = body
        self._closed = False

    def read(self) -> bytes:
        """Read the response body."""
        return self.body

    def getheader(self, name: str, default: str | None = None) -> str | None:
        """Get a response header."""
        return default

    def close(self) -> None:
        """Close the response."""
        self._closed = True


class FakeHTTPConnection:
    """A fake HTTPConnection for testing."""

    def __init__(self):
        self.closed = False
        self.requests = []
        self.responses = []
        self._response_index = 0
        self._raise_on_request = None
        self._raise_on_response = None

    def request(self, method: str, url: str, body: bytes | str, headers: dict) -> None:
        """Record a request."""
        if self._raise_on_request:
            raise self._raise_on_request
        self.requests.append({
            "method": method,
            "url": url,
            "body": body if isinstance(body, bytes) else body.encode(),
            "headers": headers,
        })

    def getresponse(self) -> FakeResponse:
        """Get the next canned response."""
        if self._raise_on_response:
            raise self._raise_on_response
        if self._response_index < len(self.responses):
            resp = self.responses[self._response_index]
            self._response_index += 1
            return resp
        # Default: empty success response
        return FakeResponse()

    def close(self) -> None:
        """Close the connection."""
        self.closed = True

    def set_response(self, response: FakeResponse) -> None:
        """Set a single response to return."""
        self.responses = [response]
        self._response_index = 0

    def set_responses(self, responses: list[FakeResponse]) -> None:
        """Set multiple responses to return in sequence."""
        self.responses = responses
        self._response_index = 0


@pytest.fixture
def fake_http_connection_factory():
    """Factory fixture for creating FakeHTTPConnection instances."""
    connections = []

    def factory() -> FakeHTTPConnection:
        conn = FakeHTTPConnection()
        connections.append(conn)
        return conn

    factory.connections = connections
    return factory


@pytest.fixture
def integration_enabled() -> bool:
    """Check if integration tests are enabled."""
    return os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") == "1"


@pytest.fixture
def integration_host() -> str:
    """Get the integration test host."""
    return os.environ.get("ELEKTRONIKON_HOST", "192.168.100.100")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    )
