# Deploy — GitHub + Pages + Telegram

Repo đích: [Huyvux12/Bugbounty_hunter](https://github.com/Huyvux12/Bugbounty_hunter)  
Code local: `E:\Dowload\project\explore\bugbounty-hunt` (chưa `git init`)  
Remote hiện **trống** — lần `git push` đầu sẽ tạo `main`.

Không commit `.env`. Không chạy Strix trên Actions.

## Đã làm / đã sửa trước khi push

Bot ingest program **public** → snapshot `data/` + site `docs/` + Telegram khi có diff.

| Nguồn | Cách |
|---|---|
| HackerOne, Bugcrowd, Intigriti, YesWeHack, Federacy | dump arkadiyt |
| HackenProof | MCP `get_program_info` + slug watchlist |

Cron 6h. Web 3 khay: Đề xuất / Dễ ăn / Mới.

Sửa cho deploy:

- Actions checkout `main` rồi `git push origin HEAD:main` (tránh detached HEAD không đẩy được snapshot)
- Telegram lỗi HTTP không làm fail ingest / không chặn commit
- Thiếu API key không spam Telegram mỗi 6 giờ
- Job `test` chạy trước `ingest`
- `docs/.nojekyll` để Pages không nuốt JSON

`python -m pytest feed-bot/tests -q` → 18 passed.

## 0. Chuẩn bị

PowerShell, đúng thư mục project (không phải thư mục bạn `git init` lúc tạo README rỗng):

```powershell
cd E:\Dowload\project\explore\bugbounty-hunt
git check-ignore -v .env
```

Phải in ra `.gitignore` — nghĩa là `.env` sẽ không bị add.

Cần: tài khoản GitHub, `.env` local (HackenProof + Telegram), bot Telegram đã `/start`.

## 1. Git — đẩy code lên GitHub

```powershell
cd E:\Dowload\project\explore\bugbounty-hunt

git init
git branch -M main
git remote add origin https://github.com/Huyvux12/Bugbounty_hunter.git

git add .
git status
```

Trong `git status` **không** được có `.env`. Được có: `feed-bot/`, `data/`, `docs/`, `.github/`, `README.md`, `DEPLOY.md`, `.env.example`.

```powershell
git commit -m "feed-bot: ingest, pages, telegram"
git push -u origin main
```

Nếu hỏi login: browser / PAT (`repo` scope), hoặc:

```powershell
gh auth login
git push -u origin main
```

Nếu remote **không trống** (đã có README dummy) và push bị reject:

```powershell
git fetch origin
git pull origin main --allow-unrelated-histories --no-edit
# nếu conflict README: giữ file local
git checkout --ours README.md
git add README.md
git commit -m "merge remote README"
git push -u origin main
```

Chỉ khi bạn chắc remote chỉ là README rác:

```powershell
git push -u origin main --force
```

Kiểm tra: https://github.com/Huyvux12/Bugbounty_hunter — thấy `feed-bot/`, `.github/workflows/feed.yml`, `docs/`.

## 2. Secrets (Telegram + HackenProof)

GitHub → repo **Bugbounty_hunter** → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

| Secret | Lấy từ |
|---|---|
| `HACKENPROOF_API_KEY` | `.env` local |
| `TELEGRAM_BOT_TOKEN` | `.env` / `@BotFather` |
| `TELEGRAM_CHAT_ID` | `.env` / `getUpdates` |

`PAGES_URL` **không bắt buộc** — workflow đã mặc định `https://huyvux12.github.io/Bugbounty_hunter/`.

Hoặc CLI (mỗi lệnh sẽ hỏi dán giá trị, không echo):

```powershell
cd E:\Dowload\project\explore\bugbounty-hunt
gh secret set HACKENPROOF_API_KEY --repo Huyvux12/Bugbounty_hunter
gh secret set TELEGRAM_BOT_TOKEN --repo Huyvux12/Bugbounty_hunter
gh secret set TELEGRAM_CHAT_ID --repo Huyvux12/Bugbounty_hunter
```

## 3. Quyền Actions (để bot commit snapshot)

**Settings** → **Actions** → **General**:

- Actions: **Allow all actions**
- **Workflow permissions**: **Read and write permissions**
- Save

Không bật branch protection trên `main` (bot cần `git push`).

## 4. GitHub Pages (web)

**Settings** → **Pages**:

- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/docs**
- Save

URL: https://huyvux12.github.io/Bugbounty_hunter/

Lần đầu có thể 1–2 phút / 404. Site đọc `docs/data/feeds.json` — có sau khi workflow ingest chạy xong.

## 5. Chạy workflow lần đầu

**Actions** → **bug bounty feed** → **Run workflow** → `main` → **Run workflow**.

Hoặc:

```powershell
gh workflow run "bug bounty feed" --repo Huyvux12/Bugbounty_hunter
gh run watch --repo Huyvux12/Bugbounty_hunter
```

Job: `test` (pytest) → `ingest` (arkadiyt + HackenProof MCP) → commit `data/` + `docs/` nếu đổi.

Cron sau đó: `0 */6 * * *` (UTC).

Log ingest có `"telegram_sent": true/false`. `false` lần đầu là bình thường nếu snapshot local đã giống dump live.

## 6. Telegram

Bot chỉ nhắn khi:

- có program **mới**, hoặc
- **scope đổi**, hoặc
- nguồn ingest **lỗi thật** (timeout, HTTP…)

Không nhắn khi im lặng / thiếu secret (`HACKENPROOF_API_KEY missing`).

Checklist:

1. Mở bot, gửi `/start` (đã làm thì bỏ qua)
2. Secrets `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` đúng
3. Chờ diff thật, hoặc xem log `telegram_sent`

Thử tay (máy local, đã có `.env`):

```powershell
cd E:\Dowload\project\explore\bugbounty-hunt
python -m pip install -e feed-bot
python -m feed_bot
```

Nếu dump không đổi so với `data/previous/`, bot vẫn không nhắn — đúng thiết kế.

## 7. Kiểm tra xong

| Cái | Kỳ vọng |
|---|---|
| Repo | file `feed-bot`, `docs`, `.github/workflows/feed.yml` |
| Actions | `test` xanh, `ingest` xanh |
| Pages | 3 khay + chip platform, ~1000 program |
| Telegram | có link Pages khi có diff |
| `.env` trên GitHub | **không** có trong file list |

## Lệnh git hay dùng sau này

```powershell
cd E:\Dowload\project\explore\bugbounty-hunt

git status
git add -A
git status                  # lại kiểm tra không có .env
git commit -m "mô tả ngắn"
git push

git pull                    # trước khi sửa nếu bot vừa commit snapshot
```

Bot Actions cũng commit vào `main` (`data/`, `docs/`). Trước khi push tay: `git pull`.

```powershell
git pull --rebase
git push
```

Xem log bot:

```powershell
git log --oneline -15
```

Commit của Actions: `feed: snapshot 2026-...`.

## Không làm

- Đưa `.env` / token lên git hoặc issue
- Bật Pages ở `/` (root) — phải **/docs**
- Trông đợi Telegram mỗi lần cron nếu không có program mới
- Crawl HackenProof HTML (Cloudflare) — chỉ MCP
