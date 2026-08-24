from feed_bot.mcp_client import as_rows, parse_tool_result


def test_parse_text_json():
    raw = {"content": [{"type": "text", "text": '{"programs": [{"slug": "web-wallet"}]}'}]}
    parsed = parse_tool_result(raw)
    assert as_rows(parsed)[0]["slug"] == "web-wallet"


def test_as_rows_nested_data():
    assert len(as_rows({"data": [{"id": 1}, {"id": 2}]})) == 2
