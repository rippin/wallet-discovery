from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpError(RuntimeError):
    message: str
    status: int | None = None
    body: str | None = None

    def __str__(self) -> str:
        suffix = f" (HTTP {self.status})" if self.status else ""
        return f"{self.message}{suffix}"


class HttpClient:
    def __init__(self, timeout: float = 20.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if params:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            url = f"{url}{'&' if '?' in url else '?'}{encoded}"
        return self._request("GET", url, None, headers)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8")
        merged = {"Content-Type": "application/json", **(headers or {})}
        return self._request("POST", url, body, merged)

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "solana-memecoin-research/0.1",
            **(headers or {}),
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url, data=body, headers=request_headers, method=method
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise HttpError(
                        f"request to {url} failed",
                        status=exc.code,
                        body=response_body[:1000],
                    ) from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
            time.sleep(0.4 * (2**attempt))
        raise HttpError(f"request to {url} failed: {last_error}") from last_error

