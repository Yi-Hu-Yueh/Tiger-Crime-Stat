# Tiger-Crime-Stat

> 臺灣 2016–2025 縣市／行政區犯罪統計 Dashboard + NVIDIA LLM 犯罪統計助理

Tiger-Crime-Stat 是一套以官方／官方來源資料為基礎的犯罪統計視覺化與 AI 查詢系統。系統提供全臺縣市與行政區層級的案件數、每十萬人口指標、排名、資料品質、長期趨勢、異常標記與重大事件背景，並透過 NVIDIA API 的 GLM 模型提供自然語言查詢與 Dashboard 控制。

## 核心原則

- 統計數字由 deterministic DataService / Tool 計算
- LLM 不自行編造或估算犯罪統計數字
- 初步行政區資料與正式縣市年度統計分開呈現
- `unavailable` 不等於 0
- 重大事件只作背景，不宣稱因果
- 使用者可在瀏覽器自行輸入 NVIDIA API Key
- API Key 不寫入專案、不寫入 browser storage、不寫入 log

---

## 1. 主要功能

### Dashboard

- 2016–2025 犯罪統計
- 全臺 22 縣市／368 行政區
- 縣市、年份、月份、案類多選
- 案件數／每十萬人口指標
- 行政區排名
- 資料品質與行政區可分配率
- 2016–2025 長期趨勢
- 異常波動標記
- 固定重大事件背景目錄
- 行政區地圖
- Map pin／hover／zoom／pan
- 左右與上下 splitter
- Dashboard 狀態與 LLM 對話同步

### LLM 犯罪統計助理

支援 NVIDIA API：

- `z-ai/glm-5.3-flash`（預設）
- `z-ai/glm-5.3`

支援：

- 自然語言查詢犯罪統計
- deterministic fast path
- Tool calling
- conversation context
- Dashboard scope synchronization
- 單獨輸入年份、行政區、案類也可同步 Dashboard
- LLM 回答後維持在「LLM 對話」workspace
- Runtime API Key 輸入
- Runtime Model selector
- NVIDIA timeout 時 deterministic fallback
- grouped「竊盜」＝住宅竊盜＋汽車竊盜＋機車竊盜

---

## 2. 資料範圍

### 年份

`2016–2025`

### 核心案類

1. 毒品
2. 強盜
3. 搶奪
4. 住宅竊盜
5. 汽車竊盜
6. 機車竊盜
7. 強制性交
8. 組織犯罪防制條例

> 「竊盜」不是第 9 個案類。在 LLM 操作中，泛稱「竊盜」表示同時選取住宅竊盜、汽車竊盜、機車竊盜。

### 主要資料來源

- 警政署 Dataset 14200：季度初步案件資料
- 人口資料：行政區年度年底戶籍人口
- 正式年度縣市統計：獨立保存與比較，不分攤到行政區
- 行政區地理資料：縣市／行政區 GeoJSON
- 重大事件：固定 2016–2025 catalog

### 資料品質語意

- `observed_positive`：有觀測案件
- `observed_zero`：明確觀測為 0
- `partial_source`：來源僅部分涵蓋
- `incomplete_assignment`：部分案件缺少行政區資訊
- `unavailable`：沒有可用資料，**不得解讀為 0**

---

## 3. 系統架構

```text
使用者瀏覽器
    │
    ├─ Dashboard UI
    │    ├─ 地圖
    │    ├─ 篩選器
    │    ├─ 趨勢圖
    │    └─ 行政區統計
    │
    └─ LLM 對話
         │
         ├─ Runtime NVIDIA API Key
         ├─ Runtime Model selector
         │
         ▼
FastAPI Backend
    │
    ├─ scope_delta / dashboard_router
    ├─ deterministic DataService / Tools
    └─ llm_service
          │
          └─ NVIDIA API
               ├─ z-ai/glm-5.3-flash
               └─ z-ai/glm-5.3
```

LLM **不在本機執行模型**。Tiger-Crime-Stat 本機負責統計計算、Tool、Dashboard、資料品質與 request orchestration；LLM inference 在 NVIDIA API 端執行。

---

## 4. 專案目錄概要

```text
Tiger-Crime-Stat/
├─ app/
│  ├─ main.py
│  ├─ data/
│  │  └─ major_events_2016_2025.py
│  ├─ services/
│  │  ├─ data_service.py
│  │  ├─ llm_service.py
│  │  ├─ llm_tools.py
│  │  ├─ chat_router.py
│  │  ├─ chat_answers.py
│  │  ├─ dashboard_actions.py
│  │  ├─ dashboard_router.py
│  │  └─ scope_delta.py
│  └─ static/
│     ├─ index.html
│     ├─ app.js
│     └─ styles.css
├─ tests/
├─ .env.example
├─ .gitignore
└─ README.md
```

---

## 5. 本機啟動

### Windows / PowerShell

```powershell
cd D:\0TIGER\6months\PythonAPIDevelopment\Tiger-Crime-Stat

& "D:\0TIGER\6months\PythonAPIDevelopment\venv_multi_query\Scripts\python.exe" `
  -m uvicorn app.main:app `
  --host 127.0.0.1 `
  --port 18082
```

啟動成功後：

```text
Uvicorn running on http://127.0.0.1:18082
```

瀏覽器：

```text
http://127.0.0.1:18082/?phase=3c
```

---

## 6. NVIDIA API Key 申請簡介

Tiger-Crime-Stat 的 LLM 功能使用 NVIDIA hosted inference API。

### 申請步驟

1. 前往 NVIDIA Build：`https://build.nvidia.com/`
2. 使用 NVIDIA 帳號登入。
3. 找到可使用的模型頁，例如 GLM-5.3-Flash 或 GLM-5.3。
4. 在模型頁尋找 **Get API Key**。
5. 建立／取得 API Key。
6. Key 通常類似：`nvapi-xxxxxxxxxxxxxxxx`
7. 複製後妥善保存。

NVIDIA 官方文件也建議 API Key 不應寫入 source code、公開 repository 或 log。

### 在 Tiger-Crime-Stat 中使用

進入 **LLM 對話**，在 `NVIDIA API Key` 欄位輸入自己的 Key。

系統設計：

- Key 只保留在目前頁面記憶體
- 不寫入 localStorage
- 不寫入 sessionStorage
- 不寫入 cookie
- 不寫入 `.env`
- 不寫入 chat history
- 不寫入 log
- 重新整理頁面後可消失

---

## 7. Model 選擇

LLM 對話頁面可直接選：

### GLM-5.3-Flash

```text
z-ai/glm-5.3-flash
```

- 預設
- 速度較快
- 適合互動式 Dashboard

### GLM-5.3

```text
z-ai/glm-5.3
```

- 完整模型
- 通常 latency 較高
- 適合較複雜分析

Model 可在 UI 直接切換，不需要重新啟動 Uvicorn。

Model priority：

```text
UI request model
    ↓
NVIDIA_MODEL environment variable
    ↓
built-in default: z-ai/glm-5.3-flash
```

---

# 8. 操作手冊

## 8.1 Dashboard 基本操作

### 縣市

點擊 `縣市（多選）`，可選一個或多個縣市。

### 年份

點擊 `年份（多選）`，可選 `2016–2025`。

### 月份

預設 `全選（12 個月）`，也可切換部分月份。

### 指標

支援：

- 案件數
- 每十萬人口案件數／加權指標

### 案類

點擊 `選擇案類` 可多選 8 個案類。已選案類以 compact chip 顯示。

---

## 8.2 地圖操作

### Hover

滑鼠移到行政區會更新行政區 detail。

### Click

單擊行政區可固定該區；再次點同一區可解除固定。

### Zoom

在地圖內使用 `Ctrl + 滑鼠滾輪`。

### Pan

拖曳地圖即可平移。

---

## 8.3 趨勢圖

長期趨勢固定顯示：

```text
2016–2025
```

上方摘要則跟隨目前篩選期間，例如：

```text
摘要統計：2024–2025
長期趨勢：2016–2025
```

---

## 8.4 重大事件

目前 catalog：

```text
2016–2025
每年 3 個全球事件 + 3 個台灣事件
```

每筆事件包含名稱、日期／期間、scope、source。

> 時間重疊不代表因果關係。

---

## 8.5 LLM 對話操作

切換到 `LLM 對話`，輸入 NVIDIA API Key，選擇 Model，即可開始。

### 查案件數

```text
2025 年臺中市北屯區住宅竊盜有幾件？
```

系統應回答 83 件，並同步 Dashboard 到：

- 臺中市
- 北屯區
- 2025
- 住宅竊盜

### 只輸入年份

```text
2022
```

保留其他 scope，只修改年份。

### 只輸入行政區

```text
北區
```

若可由目前縣市 context 明確解析，會只修改行政區。

### 只輸入案類

```text
住宅竊盜
```

保留地區／年份，只修改案類。

### 泛稱竊盜

```text
竊盜
```

系統選取：

```text
住宅竊盜
汽車竊盜
機車竊盜
```

### 多條件

```text
北區 2022 住宅竊盜
```

一次同步所有明確 scope。

### 超出資料範圍

```text
2008
```

系統不修改 Dashboard，並告知目前可查詢年份為 2016–2025。

---

## 9. LLM 與統計資料的責任分工

```text
LLM：
理解問題
整理答案
自然語言解釋
複雜意圖判斷

Python / Tool：
統計計算
案件數
人口率
排名
趨勢
資料品質
正式／初步資料區分
重大事件資料
Dashboard action
```

> 數字由 deterministic Tool 計算，LLM 不自己猜數字。

---

## 10. API Key 安全

請勿：

- 把真實 `nvapi-...` 寫進程式碼
- commit `.env`
- 把 Key 上傳 GitHub
- 把 Key 貼進 issue / README / log

公開部署時建議讓每位使用者自行在 LLM UI 輸入自己的 NVIDIA API Key。

---

## 11. 測試

```powershell
& "D:\0TIGER\6months\PythonAPIDevelopment\venv_multi_query\Scripts\python.exe" `
  -m pytest
```

測試涵蓋統計資料、DataService、LLM Tool、Dashboard action、scope delta、API Key、Model selector、frontend、map/pin、trend、data quality、workspace preservation。

---

## 12. 公開部署

Tiger-Crime-Stat 不需要在主機執行 LLM 模型。

一般 Linux hosting：

```bash
uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

公開網站建議：

```text
公開網站
    ↓
使用者自行輸入 NVIDIA API Key
    ↓
Tiger-Crime-Stat backend
    ↓
NVIDIA API
```

---

## 13. 已知限制

- 資料期間固定為 2016–2025
- 部分年度／案類屬 partial source
- 機車竊盜部分年度行政區 assignment 不完整
- 正式縣市年度統計不得分攤到行政區
- major events 只作背景
- NVIDIA hosted API latency／quota／endpoint availability 由 NVIDIA 決定
- 公開網站使用者需自行持有可用 NVIDIA API Key

---

## 14. 專案狀態與維護原則

Tiger-Crime-Stat 已具備：

- 全國犯罪統計 Dashboard
- 行政區視覺化
- 長期趨勢
- 資料品質
- 事件背景
- LLM 查詢
- Tool-based grounded statistics
- LLM 控制 Dashboard
- Runtime API Key
- Runtime Model selector

後續原則：

> 只修正阻礙實際使用的 bug 或新增明確必要需求，不為增加功能而持續擴張。
