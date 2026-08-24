from __future__ import annotations

import json
from typing import Any

import httpx

def parse_tool_result(result: Any) -> Any:
    if isinstance(result, dict) and "result" in result:
        result = result["result"]
    if isinstance(result, dict) and result.get("structuredContent") is not None:
        return result["structuredContent"]
    contents = []
    if isinstance(result, dict):
        contents = result.get("content") or []
    texts: list[str] = []
    for item in contents:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(str(item.get("text") or ""))
    blob = "\n".join(texts).strip()
    if not blob:
        return result
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return blob


def as_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        rows: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str) and item.strip():
                rows.append({"slug": item.strip()})
        return rows
    if isinstance(value, dict):
        if value.get("error"):
            return []
        for key in ("result", "programs", "items", "data", "results", "nodes", "companies", "scopes"):
            found = value.get(key)
            if isinstance(found, list):
                return as_rows(found)
            if isinstance(found, dict) and isinstance(found.get("data"), list):
                return as_rows(found["data"])
    return []


class McpHttpClient:
    def __init__(self, url: str, headers: dict[str, str], timeout: float = 60.0):
        self.url = url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        }
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0

    def initialize(self) -> Any:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "feed-bot", "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized")
        return result

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        return parse_tool_result(result)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        self._post(payload, ignore_body=True)

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        data = self._post(payload)
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"MCP error {method}: {data['error']}")
        return data.get("result") if isinstance(data, dict) else data

    def _post(self, payload: dict[str, Any], ignore_body: bool = False) -> Any:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.post(self.url, json=payload, headers=headers)
        session = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
        if session:
            self.session_id = session
        if ignore_body:
            return None
        response.raise_for_status()
        return _decode_mcp_http(response)


def _decode_mcp_http(response: httpx.Response) -> Any:
    ctype = response.headers.get("content-type", "")
    text = response.text
    if "text/event-stream" in ctype or text.lstrip().startswith("event:"):
        data_lines = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            return {}
        return json.loads(data_lines[-1])
    if not text.strip():
        return {}
    return response.json()
