# browser-automation — X.com 每日精選摘要

透過 Chrome DevTools Protocol（CDP）自動滾動 X.com，收集推文並排序，最後產生乾淨的繁體中文 HTML 摘要。

英文版文件請見 [README.md](./README.md)。

---

## 功能特色

- **CDP 無頭滾動** — 透過 CDP 驅動真實 Chrome，自動滾動 X.com 首頁，無需任何 API Key
- **智慧排分** — 整合追蹤者層級、新鮮度、關鍵字相關性、內容密度、原創性、互動數，組合成單一分數；各權重皆可設定
- **AI 摘要 + 分類** — 每批 10 篇呼叫 OpenAI Codex；每篇自動產生一句繁體中文摘要，並由 AI 分配類別（`ai`、`geopolitics`、`engineering`、`frontend`、`security`、`finance`、`other`）
- **靜態 HTML 輸出** — 產生單一 `index.html`，包含分類區塊、文章數統計和推文直連；可直接部署到 GitHub Pages 或任何靜態主機
- **Markdown 摘要** — 同步產生 `digest.md`，純 Markdown 格式，AI Agent 可直接 `GET /digest.md` 讀取，節省 token
- **自動清除** — 預設在 build 執行時刪除超過 3 天的原始捕捉目錄與摘要封存檔
- **Git 同步嘗試** — 寫入 `index.html` 和 `digest.md` 後自動執行 `git add`、`git commit`（訊息格式：`2026/4/13 summary`），並嘗試推送到設定好的 upstream，同時印出實際 git 結果
- **快照重播** — 傳入已儲存的 HTML 檔案取代即時 CDP，方便離線測試

---

## 系統需求

| 依賴項目 | 版本 |
|---------|------|
| Python | ≥ 3.11 |
| Google Chrome | 任何近期穩定版 |
| `websockets` | ≥ 12.0 |
| `openai` | ≥ 1.0 |

```bash
python3 -m pip install -r requirements.txt
```

---

## 專案結構

```
browser-automation/
├── src/
│   ├── browser/          # CDP WebSocket 驅動 + 滾動邏輯
│   ├── pipeline/
│   │   ├── filter.py     # 雜訊過濾、去重複
│   │   ├── rank.py       # 評分 / Top-N 篩選
│   │   └── summarize.py  # OpenAI 批次摘要 + AI 分類
│   ├── scheduler/
│   │   └── run_once.py   # 主要進入點
│   ├── storage/
│   │   ├── raw_store.py      # 寫入 / 清除原始捕捉
│   │   └── summary_store.py  # 寫入 / 清除摘要封存
│   ├── web/
│   │   └── build_html.py # HTML 渲染、區塊路由
│   ├── config.py         # 從 .env.local 載入設定
│   └── domain.py         # 資料類別：Post、PostRecord、SummaryBundle
├── data/                 # 執行期輸出（已加入 .gitignore）
│   ├── raw/              # 每次執行的原始捕捉（預設保留 3 天）
│   └── summaries/        # 每次執行的 HTML + JSON 封存（預設保留 3 天）
├── index.html            # 最新摘要 — 已提交並部署
├── digest.md             # 同份摘要的純 Markdown 版本 — 供 AI Agent 讀取
├── .env.local            # 本機設定（從 .env.local.example 複製）
├── .env.local.example
└── requirements.txt
```

---

## 快速開始

### 1. 安裝依賴

```bash
python3 -m pip install -r requirements.txt
```

如果你使用新的虛擬環境，先啟用它，再安裝 requirements，否則 `python` 會找不到專案依賴：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.local.example .env.local
```

打開 `.env.local`，至少設定：

```env
# OpenAI Codex Token（來自 ~/.hermes/auth.json 或你自己的金鑰）
OPENAI_API_KEY=sk-...

# 摘要模型後端與預設模型
SUMMARIZE_BACKEND=acp
SUMMARIZE_MODEL=gpt-5.4-mini
SUMMARIZE_REASONING_EFFORT=low

# CDP 連線 — 與啟動 Chrome 時使用的 port 一致
CDP_REMOTE_DEBUGGING_PORT=9333
```

完整設定說明請見[設定參數說明](#設定參數說明)。

### 3. 啟動專用 Chrome 設定檔

```bash
mkdir -p "$HOME/your-profile"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/your-profile"
```

在該視窗登入 X.com（只需設定一次）。

### 4. 執行 Pipeline

如果你是使用專案的虛擬環境，執行任何 pipeline 指令前先啟用它：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

```bash
python3 -m src.scheduler.run_once
```

腳本會依序執行：
1. 重新啟動 Chrome 分頁，避免讀到舊快取
2. 瀏覽至 `X_HOME_URL`
3. 捲動 `SCROLL_COUNT` 次（預設 80），每次暫停 `SCROLL_PAUSE_SECONDS` 秒
4. 收集、過濾、排序並摘要推文
5. 將 `index.html` 和 `digest.md` 寫入專案根目錄
6. 在 build 執行時清除超過 `RAW_RETENTION_DAYS` 天的資料
7. 嘗試執行 `git add index.html digest.md && git commit -m "YYYY/M/D summary" && git push`，並印出實際 git 結果

### 5. 從已儲存的快照重播（離線 / CI）

```bash
python3 -m src.scheduler.run_once --html-source path/to/snapshot.html
```

---

## 設定參數說明

所有設定皆在 `.env.local`，以 `.env.local.example` 為起點。

| 變數 | 預設值 | 說明 |
|-----|--------|------|
| `SUMMARIZE_BACKEND` | `acp` | 摘要後端：`acp`、`codex` 或 `openai` |
| `SUMMARIZE_MODEL` | `gpt-5.4-mini` | ACP / 直接 Codex 摘要時使用的預設模型 |
| `SUMMARIZE_REASONING_EFFORT` | `low` | 傳給 Codex 摘要流程的 reasoning level |
| `SCROLL_COUNT` | `80` | 在首頁捲動的次數 |
| `SCROLL_PAUSE_SECONDS` | `1.5` | 每次捲動之間的等待秒數 |
| `SUMMARY_TOP_N` | `50` | 送入摘要的最大推文數 |
| `SUMMARY_SENTENCE_COUNT` | `5` | 每篇摘要的目標句數（目前 prompt 中未使用）|
| `RAW_RETENTION_DAYS` | `3` | 原始捕捉與摘要封存的保留天數 |
| `SOURCE_WEIGHT_A/B/C` | `1.5 / 1.0 / 0.6` | 追蹤者層級乘數（高 / 中 / 低）|
| `FRESHNESS_WEIGHT` | `0.20` | 新鮮度權重 |
| `RELEVANCE_WEIGHT` | `0.20` | 關鍵字相關性權重 |
| `DENSITY_WEIGHT` | `0.15` | 內容長度 / 資訊密度權重 |
| `ORIGINALITY_WEIGHT` | `0.10` | 原創貼文（非轉推）權重 |
| `ENGAGEMENT_WEIGHT` | `0.05` | 按讚 + 轉推數權重 |
| `DUPLICATE_PENALTY` | `0.25` | 近似重複貼文的分數懲罰乘數 |
| `FRONTEND_BOOST_WEIGHT` | `0.18` | 對前端 / UI / browser 訊號明顯的貼文額外加權 |
| `OUTPUT_DIR` | `data/summaries` | 摘要封存根目錄 |
| `RAW_DIR` | `data/raw` | 原始捕捉根目錄 |
| `X_HOME_URL` | `https://x.com/` | 要爬取的動態頁面網址 |
| `FOCUS_KEYWORDS` | （空）| 以逗號分隔的關鍵字，可提升相關性分數 |
| `DELETE_RAW_AFTER_SUMMARY` | `false` | 摘要完成後立即刪除原始執行目錄 |
| `CDP_REMOTE_DEBUGGING_HOST` | `localhost` | Chrome CDP 主機 |
| `CDP_REMOTE_DEBUGGING_PORT` | `9333` | 範例設定檔中的 Chrome CDP 埠號；若未設定，runtime 預設為未指定 |
| `CDP_TARGET_URL` | `about:blank` | CDP 附接的初始分頁網址 |

---

## 排程設定（cron）

每次觸發都會進行資料收集。程式內部維護一個計數器，**當天第三次執行時自動 build**（合併當日所有資料 → 寫入 `index.html` 與 `digest.md` → 嘗試 git push），不需要額外的指令旗標。

```cron
# 第 1 次 — 早上收集
0 10 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1

# 第 2 次 — 下午收集
0 16 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1

# 第 3 次 — 晚上收集 + 自動 build + git 同步嘗試（摘要當晚發布）
0 22 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1
```

每天晚上約 22:00 報告上線，早上起床即可查看前一天的摘要。

如需立即強制 build（不等計數器）：

```bash
source .venv/bin/activate
python3 -m src.scheduler.run_once --force-build
```

如果只想用既有 raw 資料直接 build，不重新收集、也不啟動 Chrome：

```bash
source .venv/bin/activate
python3 -m src.scheduler.run_once --build-only
```

目前摘要預設會透過 ACP Python SDK 在 stdio 上啟動 repo 內建的 Codex bridge agent；它不是常駐程序，而是每次摘要呼叫時啟動、完成後結束。該 bridge 預設使用 `gpt-5.4-mini` 與 `low` reasoning，可透過 `.env.local` 覆寫。

---

## 推文分類

推文由 LLM 自動分配到以下類別之一：

| 類別 | 區塊標題 |
|------|---------|
| `ai` | 🤖 AI 模型與工具 |
| `geopolitics` | 🌐 地緣政治 |
| `engineering` | ⚙️ 軟體工程 |
| `frontend` | 🖥️ 前端開發 |
| `security` | 🔐 資安 |
| `finance` | 💰 財經 |
| `other` | 📌 其他 |

若 LLM 回傳無效的類別，該推文會退回關鍵字比對，最後回落到 `other`。

---

## 注意事項

- `index.html` 已提交至 git，作為公開摘要頁面使用
- `digest.md` 與 `index.html` 一同提交 — AI Agent 可直接存取 `https://你的網域/digest.md`，以純 Markdown 格式讀取摘要，節省 token
- `data/` 已加入 `.gitignore`，所有執行期產物只保留在本機
- Chrome 設定檔會在執行之間保留登入狀態，第一次登入後無需重新驗證
- 若 CDP 無法連線，Pipeline 會在早期即報錯退出，不會產生部分寫入的輸出
