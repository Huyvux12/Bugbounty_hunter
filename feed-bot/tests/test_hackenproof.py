from feed_bot.mcp_client import as_rows
from feed_bot.sources.hackenproof import fetch_hackenproof, _slug_from_url


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, arguments=None):
        arguments = arguments or {}
        self.calls.append((name, arguments))
        if name == "list_companies":
            return {"result": []}
        if name == "get_program_info":
            slug = arguments.get("program")
            if slug == "hackenproof":
                return {
                    "program": "hackenproof",
                    "title": "HackenProof",
                    "state": "published",
                    "status": {"name": "Active"},
                    "rewards": {"critical_max": 1500, "low_min": 50},
                    "scopes": [
                        {
                            "out_of_scope": False,
                            "target": "Main website",
                            "target_description": "https://hackenproof.com",
                            "title": "Web",
                        }
                    ],
                }
            return {"error": "404", "program": slug}
        raise AssertionError(name)


def test_as_rows_result_and_slugs():
    assert as_rows({"result": []}) == []
    assert as_rows(["web-wallet", "hackenproof"]) == [
        {"slug": "web-wallet"},
        {"slug": "hackenproof"},
    ]


def test_slug_from_url():
    assert _slug_from_url("https://hackenproof.com/programs/bingx-exchange") == "bingx-exchange"
    assert _slug_from_url("https://hackenproof.com/1inch/1inch-smart-contract") == "1inch-smart-contract"
    assert _slug_from_url("hackenproof") == "hackenproof"


def test_fetch_uses_watchlist_when_companies_empty(monkeypatch):
    fake = FakeMcp()
    rows = fetch_hackenproof(
        api_key="test-key",
        client_factory=lambda: fake,
        slugs=["hackenproof", "missing-slug"],
        discover=False,
    )
    assert [r["slug"] for r in rows] == ["hackenproof"]
    assert ("get_program_info", {"program": "hackenproof"}) in fake.calls
    assert rows[0]["title"] == "HackenProof"
