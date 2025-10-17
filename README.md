# Statin Recommendation API

這是一個使用 FastAPI 建構的輕量級後端 API，旨在根據臨床數據提供 Statin 藥物治療建議。它是一個純後端服務，專為前後端分離的架構而設計。

## ✨ 功能

- **基於 FastAPI**: 擁有高效能和異步處理能力。
- **Pydantic 驗證**: 自動對傳入的請求數據進行類型檢查和驗證。
- **自動化 API 文件**: 內建 Swagger UI 和 ReDoc，方便測試和查閱。
- **前後端分離**: 作為一個獨立的邏輯引擎，可以與任何前端框架（如 React, Vue, Angular）或客戶端輕鬆整合。

---

## 🚀 開始使用

請依照以下步驟在您的本地環境中設定並執行此專案。

### 1. 環境準備

- 確認您已安裝 Python 3.8 或更高版本。
- 建議使用虛擬環境來管理專案依賴。

### 2. 安裝

首先，複製此專案（或在您的專案目錄中）：

```bash
# 建立並啟用虛擬環境 (macOS/Linux)
python3 -m venv venv
source venv/bin/activate

# 建立並啟用虛擬環境 (Windows)
python -m venv venv
.\venv\Scripts\activate
```

接著，安裝所有必要的依賴項：

```bash
pip install -r requirements.txt
```

### 3. 執行應用程式

使用 Uvicorn 來啟動 API 伺服器：

```bash
uvicorn app:app --reload
```

伺服器將會在 `http://127.0.0.1:8010` 上運行。`--reload` 參數會讓伺服器在您修改程式碼後自動重啟，非常適合開發。

---

## 📚 API 使用說明

### `GET /`

提供 API 的基本資訊。

### `POST /evaluate`

這是此 API 的核心端點，用於獲取診斷建議。

**請求主體 (Request Body):**

```json
{
  "ck_value": 250.5,
  "transaminase": 35.0,
  "bilirubin": 1.2,
  "muscle_symptoms": false
}
```

**範例請求 (cURL):**

```bash
curl -X POST "http://127.0.0.1:8010/evaluate" \
-H "Content-Type: application/json" \
-d '{"ck_value": 250.5, "transaminase": 35.0, "bilirubin": 1.2, "muscle_symptoms": false}'
```

### 互動式 API 文件

當伺服器運行時，您可以直接在瀏覽器中訪問 http://127.0.0.1:8010/docs 來查看由 FastAPI 自動生成的互動式 Swagger UI 文件。您可以在此頁面上直接測試所有 API 端點。