"""HTTP transport for communicating with Elektronikon controllers."""

import http.client
import socket
import urllib.parse
from typing import Callable

from pytronikon.codec import Answer, Selector, decode_raw_value, normalize_selector, split_aligned_answers
from pytronikon.errors import ElektronikonHttpError


class ElektronikonTransport:
    """HTTP transport for Elektronikon mkv.cgi protocol."""

    def __init__(
        self,
        host: str,
        timeout: float = 5.0,
        batch_size: int = 1000,
        connection_factory: Callable[[], http.client.HTTPConnection] | None = None,
    ) -> None:
        """Initialize the transport.

        Args:
            host: The hostname or IP address (with optional :port).
            timeout: The socket timeout in seconds.
            batch_size: Maximum selectors per request.
            connection_factory: Optional callable that returns an HTTPConnection.
                If not provided, a default factory is created.
        """
        # Parse host and port
        if ":" in host:
            self.host, port_str = host.rsplit(":", 1)
            try:
                self.port = int(port_str)
            except ValueError:
                self.host = host
                self.port = 80
        else:
            self.host = host
            self.port = 80

        self.timeout = timeout
        self.batch_size = batch_size
        self._connection: http.client.HTTPConnection | None = None

        if connection_factory is None:
            self.connection_factory = lambda: http.client.HTTPConnection(
                self.host,
                self.port,
                timeout=self.timeout,
            )
        else:
            self.connection_factory = connection_factory

    def _get_connection(self) -> http.client.HTTPConnection:
        """Get or create the persistent connection."""
        if self._connection is None:
            self._connection = self.connection_factory()
        return self._connection

    def _close_connection(self) -> None:
        """Close the persistent connection."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def close(self) -> None:
        """Close the transport connection."""
        self._close_connection()

    def __enter__(self) -> "ElektronikonTransport":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    def fetch_text(self, path: str) -> str:
        """Fetch a text resource from the controller.

        Args:
            path: The path to fetch (e.g., "/languages/English.txt").

        Returns:
            The response body as a string.

        Raises:
            ElektronikonHttpError: If the request fails.
        """
        if not path.startswith("/"):
            path = "/" + path

        return self._request("GET", path, b"", {})

    def query_selectors(self, selectors: str | int | list[Selector] | list[str]) -> list[Answer]:
        """Query one or more selectors from the controller.

        Args:
            selectors: A list of Selector objects or selector strings.

        Returns:
            A list of Answer objects in the same order.

        Raises:
            ElektronikonHttpError: If the request fails.
        """
        # Normalize selectors
        normalized = [normalize_selector(s) if isinstance(s, str) else s for s in selectors]

        results = []
        for offset in range(0, len(normalized), self.batch_size):
            batch = normalized[offset : offset + self.batch_size]
            results.extend(self._query_batch(batch))

        return results

    def _query_batch(self, selectors: list[Selector]) -> list[Answer]:
        """Query a single batch of selectors."""
        # Build the QUESTION parameter by concatenating all selector keys
        question = "".join(s.key for s in selectors)

        # Build the request body
        body = urllib.parse.urlencode({"QUESTION": question}).encode("utf-8")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        response_text = self._request("POST", "/cgi-bin/mkv.cgi", body, headers)

        # Parse the response
        answers = split_aligned_answers(selectors, response_text)

        # Decode each answer's raw value
        return [
            Answer(
                key=answer.key,
                index=answer.index,
                subindex=answer.subindex,
                raw=answer.raw,
                meta=answer.meta,
            )
            for answer in answers
        ]

    def _request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> str:
        """Make an HTTP request with reconnect-and-retry-once semantics.

        Args:
            method: HTTP method ("GET" or "POST").
            path: The request path.
            body: The request body (empty bytes for GET).
            headers: HTTP headers dict.

        Returns:
            The response body as a string.

        Raises:
            ElektronikonHttpError: If the request fails.
        """
        for attempt in range(2):
            try:
                conn = self._get_connection()
                conn.request(method, path, body, headers)
                response = conn.getresponse()
                response_data = response.read()

                # Check the response status
                if response.status < 200 or response.status >= 300:
                    raise ElektronikonHttpError(
                        f"Unexpected HTTP status {response.status} for {path}",
                        {
                            "url": f"http://{self.host}:{self.port}{path}",
                            "status": response.status,
                            "status_text": response.reason,
                        },
                    )

                # Check for Connection: close header
                if response.getheader("connection", "").lower() == "close":
                    self._close_connection()

                # Decode and return
                return response_data.decode("utf-8")

            except ElektronikonHttpError:
                # Already an Elektronikon error; don't retry
                raise
            except (
                http.client.RemoteDisconnected,
                http.client.BadStatusLine,
                ConnectionResetError,
                BrokenPipeError,
            ) as e:
                # Connection loss — close and retry once
                self._close_connection()
                if attempt == 1:
                    # Second attempt failed
                    raise ElektronikonHttpError(
                        "Unable to complete mkv.cgi request",
                        {
                            "url": f"http://{self.host}:{self.port}{path}",
                        },
                        e,
                    ) from e
                # Loop to retry
                continue
            except socket.timeout as e:
                # Timeout — don't retry
                raise ElektronikonHttpError(
                    f"Request timeout for {path}",
                    {
                        "url": f"http://{self.host}:{self.port}{path}",
                    },
                    e,
                ) from e
            except (OSError, http.client.HTTPException) as e:
                # Other HTTP/OS errors
                self._close_connection()
                if attempt == 1:
                    raise ElektronikonHttpError(
                        "Unable to complete mkv.cgi request",
                        {
                            "url": f"http://{self.host}:{self.port}{path}",
                        },
                        e,
                    ) from e
                # Loop to retry
                continue

            except ElektronikonHttpError:
                # Already an Elektronikon error; don't retry
                raise
            except (
                http.client.RemoteDisconnected,
                http.client.BadStatusLine,
                ConnectionResetError,
                BrokenPipeError,
            ) as e:
                # Connection loss — close and retry once
                self._close_connection()
                if attempt == 1:
                    # Second attempt failed
                    raise ElektronikonHttpError(
                        "Unable to complete mkv.cgi request",
                        {
                            "url": f"http://{self.host}:{self.port}{path}",
                        },
                        e,
                    ) from e
                # Loop to retry
                continue
            except socket.timeout as e:
                # Timeout — don't retry
                raise ElektronikonHttpError(
                    f"Request timeout for {path}",
                    {
                        "url": f"http://{self.host}:{self.port}{path}",
                    },
                    e,
                ) from e
            except (OSError, http.client.HTTPException) as e:
                # Other HTTP/OS errors
                self._close_connection()
                if attempt == 1:
                    raise ElektronikonHttpError(
                        "Unable to complete mkv.cgi request",
                        {
                            "url": f"http://{self.host}:{self.port}{path}",
                        },
                        e,
                    ) from e
                # Loop to retry
                continue

        # Should not reach here, but fail if we do
        raise ElektronikonHttpError(
            "Unable to complete mkv.cgi request",
            {"url": f"http://{self.host}:{self.port}{path}"},
        )
