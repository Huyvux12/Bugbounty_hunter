# Bug bounty feed bot

Feed program bug bounty **public**: HackerOne, Bugcrowd, Intigriti, YesWeHack và các program self-host.

GitHub Actions (cron 6h) ingest scope/rules → snapshot trên repo → 3 khay **Đề xuất / Dễ ăn / Mới** trên GitHub Pages và Telegram khi có program mới hoặc scope đổi.

Không chạy Strix. Không crawl Cloudflare. Không dùng MCP local.

## Nguồn

| Nền tảng | Cách |
|---|---|
| HackerOne, Bugcrowd, Intigriti, YesWeHack | dump [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data) |
| Self-host | dump disclose.io + ProjectDiscovery + lissy93/bug-bounties (lọc URL nền tảng). LLM (tùy chọn) dịch/nhãn thưởng |

Federacy và HackenProof đã được loại khỏi pipeline; không cần API key HackenProof. Snapshot mới bỏ các program của hai nguồn này, giữ lịch sử cũ và không tạo sự kiện program đóng do việc loại nguồn.

Số program thay đổi theo nguồn ở mỗi lần ingest; trạng thái và số lượng thực tế hiển thị trên Pages.

## Pipeline

```text
cron 6h
  → arkadiyt JSON + dump self-host
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
```

`.env` (gitignore):

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
PAGES_URL=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gemini-3.5-flash-lite
LLM_RPM=15
LLM_MAX_PER_RUN=180
```

Pages: lọc asset (url/wildcard/…) + loại thưởng; tab **Đã lưu** + note trên máy (`localStorage`, export/import JSON).

Self-host giữ toàn bộ program sau khi gộp trùng; Pages hiển thị mỗi lần 50 mục. Lần đầu bỏ giới hạn 500, các program được bổ sung được đánh dấu backfill để không tạo thông báo "program mới" giả. AI là bước tùy chọn trên GitHub Actions, chỉ bổ sung self-host dựa trên metadata từ các nguồn tổng hợp (không đọc policy live); `LLM_BASE_URL` cần là URL gốc tương thích OpenAI, có hoặc không có hậu tố `/v1`. Số mục đã xử lý, chờ và lỗi hiển thị trên Pages. `LLM_MAX_PER_RUN` đặt qua GitHub Actions variable, mặc định 180, tối đa 300. Không đưa khóa API vào repo; đặt `LLM_API_KEY` trong Actions Secrets.

Telegram: `@BotFather` → token; mở bot `/start` rồi `getUpdates` lấy `chat.id`. Bot chỉ nhắn khi có diff.

GitHub: Pages = `main` / `docs`. Secrets trùng `.env`. Workflow: `.github/workflows/feed.yml`.

Kiểm tra giao diện: `node --test docs/tests/app.test.cjs` (Node.js 22).

## Thư mục

```text
feed-bot/     ingest, rank, telegram, tests
data/         snapshot programs + feeds + diff
docs/         GitHub Pages
```




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

## Scopeboard — phát triển giao diện

Giao diện dashboard hỗ trợ mobile, tìm kiếm domain/scope, sắp xếp, bộ lọc theo đơn vị thưởng, liên kết chia sẻ đến program và khôi phục trạng thái qua Back/Forward. “Dễ tiếp cận” là điểm heuristic từ metadata, không phải xác suất tìm được lỗi.

```sh
npm ci
npm test
npx playwright install --with-deps chromium
npm run test:e2e
python -m http.server 4173 --directory docs
```

Trình duyệt test gồm desktop 1280 px, tablet 768 px, mobile 390 px và 360 px; kiểm tra cả accessibility, retry, deep link, import/export và lỗi storage. Nếu môi trường đã có Chromium, đặt `PLAYWRIGHT_CHROMIUM_EXECUTABLE` tới executable thay vì cài browser khác. Bộ kiểm thử dùng snapshot trong checkout, không gửi Telegram và không gọi nguồn ingest live.

Ghi chú và bookmark lưu trên thiết bị, không đồng bộ qua tài khoản. Export dùng schema `version: 1`; import tương thích bản cũ, xem số mục trùng trước khi gộp, tối đa 2 MB / 5.000 mục / 20.000 ký tự mỗi note. Khi storage bị đầy/chặn, giao diện giữ thay đổi trong phiên và yêu cầu xuất bản sao; không thông báo lưu thành công giả. Program rời feed vẫn còn trong bộ sưu tập nếu đã lưu.

## Snapshot và vận hành

`publish_docs` tiếp tục xuất JSON cũ để tương thích, đồng thời tạo `docs/data/manifest.json` trỏ tới một snapshot bất biến trong `docs/data/snapshots/`. Index nhẹ dùng cho danh sách và tìm kiếm; scope được tải theo bucket khi mở chi tiết, lịch sử chỉ tải khi cần. Manifest được ghi cuối, frontend kiểm tra `schema_version` và `snapshot_id` để tránh trộn dữ liệu giữa các lần publish. Giữ snapshot hiện tại và hai phiên bản trước; tab mở lâu hơn cần tải lại nếu chi tiết cũ không còn. Không chỉnh tay các artifact được sinh tự động.

Ingest khóa thư mục data để tránh hai writer, dùng lại HTTP connection và retry tối đa ba lần cho timeout/408/429/5xx có thể phục hồi. Không retry 404/401. `Retry-After` quá 10 giây được hoãn đến lần ingest sau thay vì gọi lại sớm. Bản ghi lỗi trong dump self-host được đếm và giữ lại các bản tốt; nguồn chưa đầy đủ vẫn giữ dữ liệu tốt gần nhất và làm CLI báo lỗi. Trạng thái có thời lượng xử lý từng nguồn.

Outbox vẫn giữ checkpoint từng phần, backoff sau lỗi gửi và gộp cảnh báo nguồn giống nhau đang chờ khi không có thay đổi program. Không tự xóa backlog cũ; `--no-telegram` không gửi hoặc thêm thông báo và vẫn giữ hàng đợi.
