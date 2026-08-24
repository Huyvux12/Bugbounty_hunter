from __future__ import annotations

import json
import os
from typing import Any

from feed_bot.mcp_client import McpHttpClient, as_rows
from feed_bot.sources.hackenproof import DEFAULT_URL


def _preview(value: Any, limit: int = 4000) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"truncated": True, "chars": len(text), "head": text[:limit]}


def _safe_preview(value: Any, limit: int = 6000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) > limit:
        return text[:limit] + "\n… [truncated]"
    return text


def probe() -> dict[str, Any]:
    key = os.environ.get("HACKENPROOF_API_KEY")
    if not key:
        raise SystemExit("Thiếu HACKENPROOF_API_KEY. Thêm vào .env ở root repo rồi chạy lại.")

    url = os.environ.get("HACKENPROOF_MCP_URL") or DEFAULT_URL
    client = McpHttpClient(url, {"X-Api-Key": key})
    init = client.initialize()
    tools = []
    try:
        listed = client.request("tools/list")
        tools = listed.get("tools") if isinstance(listed, dict) else listed
    except Exception as exc:
        tools = [{"error": str(exc)}]

    report: dict[str, Any] = {
        "mcp_url": url,
        "key_present": True,
        "key_length": len(key),
        "initialize": _preview(init, 1500),
        "tools": [
            {
                "name": t.get("name") if isinstance(t, dict) else t,
                "description": (t.get("description") or "")[:240] if isinstance(t, dict) else "",
                "inputSchema": t.get("inputSchema") if isinstance(t, dict) else None,
            }
            for t in (tools or [])
        ],
        "calls": {},
    }

    def call(name: str, arguments: dict[str, Any] | None = None) -> Any:
        try:
            return client.call_tool(name, arguments)
        except Exception as exc:
            return {"error": str(exc)}

    companies = call("list_companies")
    report["calls"]["list_companies"] = {
        "row_count": len(as_rows(companies)),
        "keys": sorted({k for row in as_rows(companies) for k in row.keys()}),
        "preview": companies if isinstance(companies, dict) and companies.get("error") else _preview(companies, 5000),
    }

    programs = call("list_programs")
    if isinstance(programs, dict) and programs.get("error"):
        first_company = as_rows(companies)[0] if as_rows(companies) else {}
        cid = str(first_company.get("id") or first_company.get("slug") or first_company.get("handle") or "")
        if cid:
            programs = call("list_programs", {"company_id": cid, "companyId": cid})
    program_rows = as_rows(programs)
    report["calls"]["list_programs"] = {
        "row_count": len(program_rows),
        "keys": sorted({k for row in program_rows for k in row.keys()}),
        "preview": programs if isinstance(programs, dict) and programs.get("error") else _preview(programs, 5000),
    }

    first = program_rows[0] if program_rows else {}
    program_id = str(first.get("id") or first.get("slug") or first.get("handle") or first.get("program_id") or "")
    if program_id:
        info = call("get_program_info", {"program_id": program_id, "programId": program_id})
        info_dict = info if isinstance(info, dict) else {"value": info}
        report["calls"]["get_program_info"] = {
            "program_id": program_id,
            "keys": sorted(info_dict.keys()),
            "preview": _preview(info, 8000),
        }
    else:
        report["calls"]["get_program_info"] = {"error": "no program id from list_programs"}

    return report


def main() -> int:
    report = probe()
    print(_safe_preview(report, 20000))
    return 0
