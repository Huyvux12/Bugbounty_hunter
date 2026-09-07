# Bug bounty feed bot

Feed program bug bounty **public**: HackerOne, Bugcrowd, Intigriti, YesWeHack, Federacy, HackenProof.

GitHub Actions (cron 6h) ingest scope/rules → snapshot trên repo → 3 khay **Đề xuất / Dễ ăn / Mới** trên GitHub Pages và Telegram khi có program mới hoặc scope đổi.

Không chạy Strix. Không crawl Cloudflare. Không dùng MCP local.

## Nguồn

| Nền tảng | Cách |
|---|---|
| HackerOne, Bugcrowd, Intigriti, YesWeHack, Federacy | dump [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data) |
| HackenProof | MCP hosted `get_program_info` (researcher key không list directory). Slug: `feed-bot/watchlists/hackenproof_slugs.txt` + [public-bugbounty-programs](https://github.com/projectdiscovery/public-bugbounty-programs) |
| Self-host | dump disclose.io + ProjectDiscovery + lissy93/bug-bounties (lọc URL nền tảng). LLM (tùy chọn) dịch/nhãn thưởng |

Ingest gần nhất: ~1000 program (H1 448, Bugcrowd 260, Intigriti 136, YWH 63, Federacy 35, HackenProof 65).

## Pipeline

```text
cron 6h
  → arkadiyt JSON + HackenProof MCP + dump self-host
  → schema chung, loại wildcard/CIDR/mobile khỏi “quét được”
  → điểm dễ ăn, 3 khay, diff snapshot
  → commit data/ + docs/
  → Telegram nếu có program mới / scope đổi / nguồn lỗi
```

**Đề xuất:** round-robin theo nền tảng (không để HackerOne át hết). Pages có chip lọc từng platform.

## Chạy

```powershell
python -m pip install -e feed-bot[dev]
python -m pytest feed-bot/tests -q
python -m feed_bot --no-telegram
python -m feed_bot --probe-hackenproof
```

`.env` (gitignore):

```env
HACKENPROOF_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
PAGES_URL=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gemini-3.5-flash-lite
```

Pages: lọc asset (url/wildcard/…) + loại thưởng; tab **Đã lưu** + note trên máy (`localStorage`, export/import JSON).

Telegram: `@BotFather` → token; mở bot `/start` rồi `getUpdates` lấy `chat.id`. Bot chỉ nhắn khi có diff.

GitHub: Pages = `main` / `docs`. Secrets trùng `.env`. Workflow: `.github/workflows/feed.yml`.

Deploy (git + Pages + Telegram): [DEPLOY.md](DEPLOY.md)

## Thư mục

```text
feed-bot/     ingest, rank, telegram, tests
data/         snapshot programs + feeds + diff
docs/         GitHub Pages
```

Thêm program HackenProof: một slug/dòng trong `feed-bot/watchlists/hackenproof_slugs.txt`.
