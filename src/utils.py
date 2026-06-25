"""Utility functions for Application Tracker."""

import httplib2
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.auth.transport.requests import AuthorizedSession


class _RequestsToHttplib2Adapter:
    """
    Wraps a requests.Session to present the httplib2.Http interface
    expected by google-api-python-client.

    This lets us benefit from:
      - urllib3's superior SSL handling on Windows (avoids httplib2 SSLEOFError)
      - Connection pooling: fewer SSL handshakes per session
      - HTTPAdapter-level retries on connection resets and SSL failures
        *before* exceptions propagate into application code
    """

    def __init__(self, session: requests.Session):
        self._session = session

    def request(
        self,
        uri,
        method="GET",
        body=None,
        headers=None,
        redirections=5,
        connection_type=None,
    ):
        resp = self._session.request(
            method=method,
            url=uri,
            data=body,
            headers=headers or {},
            allow_redirects=(redirections > 0),
        )

        # Build an httplib2-compatible Response object.
        # httplib2.Response is a dict subclass; passing headers + "status"
        # key gives it the right .status attribute and dict-style header access.
        headers_dict = dict(resp.headers)
        headers_dict["status"] = str(resp.status_code)
        http2_resp = httplib2.Response(headers_dict)
        http2_resp.status = resp.status_code
        http2_resp.reason = resp.reason

        return http2_resp, resp.content

    # Some googleapiclient internals inspect .connections on the http object
    @property
    def connections(self):
        return {}


def build_authorized_http(credentials):
    """
    Create an httplib2-compatible HTTP transport backed by requests + urllib3,
    with automatic retry on transient network/SSL failures.

    Retry strategy (all handled at the urllib3/connection-pool level):
      - 5 total retries with exponential backoff: 1s, 2s, 4s, 8s, 16s
      - Retries on HTTP 429, 500, 502, 503, 504 status codes
      - Retries on connection errors, read errors (catches SSL EOF on Windows)
      - Respects Retry-After response headers
    """
    session = AuthorizedSession(credentials)

    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE"],
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return _RequestsToHttplib2Adapter(session)
