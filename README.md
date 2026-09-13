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
LLM_RPM=15
```

Pages: lọc asset (url/wildcard/…) + loại thưởng; tab **Đã lưu** + note trên máy (`localStorage`, export/import JSON).

Telegram: `@BotFather` → token; mở bot `/start` rồi `getUpdates` lấy `chat.id`. Bot chỉ nhắn khi có diff.

GitHub: Pages = `main` / `docs`. Secrets trùng `.env`. Workflow: `.github/workflows/feed.yml`.

Kiểm tra giao diện: `node --test docs/tests/app.test.cjs` (Node.js 22).

## Thư mục

```text
feed-bot/     ingest, rank, telegram, tests
data/         snapshot programs + feeds + diff
docs/         GitHub Pages
```

Thêm program HackenProof: một slug/dòng trong `feed-bot/watchlists/hackenproof_slugs.txt`.



## Độ tin cậy và các chức năng mới

- **Tải thiếu dữ liệu:** mỗi nguồn/slug có trạng thái complete, partial hoặc failed. Bản ghi lỗi và phản hồi rỗng bất thường không được coi là bằng chứng program đã bị xóa. Bản tốt gần nhất được giữ lại với `stale=true` và `last_seen` cũ; các program này không vào khay Đề xuất/Dễ ăn/Mới. Khi nguồn phục hồi, dữ liệu mới thay thế dữ liệu cũ.
- **Lịch sử:** ghi program mới/biến mất, thay đổi scope trong/ngoài, điều kiện nhận báo cáo/bounty, trạng thái, mức thưởng, đơn vị, policy và contact. Xem lịch sử từng program trong hộp chi tiết hoặc mở Lịch sử thay đổi ở đầu trang. Giao diện hiển thị tối đa 100 mục gần nhất; file JSON có toàn bộ lịch sử từ khi tính năng bắt đầu chạy. Lịch sử cũ trước đó không được tự suy diễn.
- **Lưu an toàn:** snapshot chính là checkpoint cho programs, history, outbox và quality. Ghi file tạm cùng thư mục, flush/fsync, rồi thay thế nguyên tử. Đọc bản backup nếu snapshot chính bị hỏng; không ghi đè backup tốt bằng file hỏng. Nếu cả hai hỏng, dừng để tránh mất lịch sử. Các file Pages/feed là bản xuất có thể tạo lại; nhiều file không phải một giao dịch nguyên tử.
- **Telegram:** thông báo chờ gửi được lưu cùng snapshot trước khi gửi. Tin dài được chia nhỏ; mỗi phần gửi thành công có checkpoint riêng. Lần chạy tiếp theo thử lại hàng đợi kể cả khi không có diff mới; tối đa 10 digest mỗi lần chạy. Thiếu token/chat ID thì giữ hàng đợi. `--no-telegram` không gửi và không xếp hàng sự kiện mới, nhưng giữ hàng đợi đã có. Nếu tiến trình dừng đúng sau khi Telegram nhận tin nhưng trước khi lưu checkpoint, một phần tin có thể được gửi lại (at-least-once).
- **Bộ lọc thưởng:** chọn đơn vị trước khi đặt “Thưởng tối đa từ”. Chỉ so sánh `max_bounty` đã biết trong đúng đơn vị đó; không quy đổi tỷ giá và không dùng `min_bounty` thay mức tối đa.
- **Chất lượng:** `data/quality.json`, đầu ra CLI và Pages hiển thị số bản ghi bị lỗi/bỏ qua, dữ liệu cũ, nguồn chưa đầy đủ và thông báo chờ gửi. Trạng thái nguồn có thời điểm thành công gần nhất và chi tiết nguồn con/slug lỗi.
- **Kiểm tra đầu vào:** YAML dùng SafeLoader, danh sách asset phải là list chuỗi; nhận diện repo/mobile theo hostname. Mức thưởng phải là số hữu hạn không âm, min không vượt max. Cache LLM dựa vào cả đầu vào thưởng; thay đổi hash có thể làm cache cũ được làm mới trong giới hạn enrichment mỗi lần chạy.

Nguồn tự trả dữ liệu thiếu nhưng vẫn báo thành công và không có dấu hiệu lỗi không thể luôn được nhận biết; cần theo dõi thống kê và policy gốc. Khi một nguồn không đầy đủ, việc xác nhận program biến mất được hoãn đến khi có dữ liệu đầy đủ. Không chạy đồng thời nhiều tiến trình ghi cùng thư mục data; workflow GitHub đã có concurrency group.

Workflow `test.yml` chạy test cho pull request và main. Workflow ingest vẫn commit checkpoint khi lần ingest trả lỗi, sau đó đánh dấu job thất bại để vừa giữ hàng đợi/dữ liệu vừa báo lỗi vận hành.
