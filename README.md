---
title: Product Manager - Equipment & Signboard Inventory
emoji: 🏭
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
license: mit
---

# Product Manager

Equipment and signboard inventory management system with OCR capabilities.

## Features
- Equipment management with image upload
- Signboard inventory tracking
- OCR text extraction from images
- Web search for equipment manuals/specifications
- JSON bulk import with automatic product image search

## Database Setup (Supabase - 無料)

データを永続化するには、Supabase（無料）を使用します。

### 1. Supabaseプロジェクトの作成

1. [Supabase](https://supabase.com/) でアカウント作成
2. 「New Project」でプロジェクトを作成
3. Project Settings → API から以下を取得:
   - **Project URL** (例: `https://xxxxx.supabase.co`)
   - **anon public key** (API Keys セクション)

### 2. テーブルの作成

Supabase Dashboard の SQL Editor で以下を実行:

```sql
-- 機器テーブル
CREATE TABLE equipment (
    id SERIAL PRIMARY KEY,
    equipment_name TEXT,
    model_number TEXT,
    serial_number TEXT,
    purchase_date TEXT,
    tool_category TEXT,
    manufacturer TEXT,
    weight TEXT,
    output_power TEXT,
    engine_model TEXT,
    year_manufactured TEXT,
    specifications TEXT,
    raw_text TEXT,
    ocr_engine TEXT,
    llm_engine TEXT,
    file_name TEXT,
    image_path TEXT,
    quantity INTEGER DEFAULT 1,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 看板テーブル
CREATE TABLE signboards (
    id SERIAL PRIMARY KEY,
    comment TEXT,
    description TEXT,
    size TEXT,
    quantity INTEGER DEFAULT 1,
    location TEXT,
    status TEXT DEFAULT '在庫あり',
    notes TEXT,
    image_path TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 看板数量履歴テーブル
CREATE TABLE signboard_quantity_history (
    id SERIAL PRIMARY KEY,
    signboard_id INTEGER NOT NULL REFERENCES signboards(id),
    change_type TEXT NOT NULL,
    change_amount INTEGER NOT NULL,
    quantity_before INTEGER NOT NULL,
    quantity_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT
);

-- API使用量テーブル
CREATE TABLE api_usage (
    id SERIAL PRIMARY KEY,
    api_name TEXT NOT NULL,
    year_month TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0,
    free_limit INTEGER DEFAULT 1000,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(api_name, year_month)
);
```

### 3. Storage Bucketの作成（画像保存用）

1. Supabase Dashboard の左メニューから「Storage」をクリック
2. 「New bucket」をクリック
3. 以下を設定:
   - **Name**: `product-images`
   - **Public bucket**: ON（チェックを入れる）
4. 「Create bucket」をクリック

### 4. HuggingFace Spaceに環境変数を設定

Space Settings → Repository secrets で以下を追加:

| Name | Value |
|------|-------|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` (Project URL) |
| `SUPABASE_KEY` | `sb_secret_...` (Secret key) |

> **Note**: 画像アップロードにはSecret keyが必要です（anon keyでは権限不足）

### 5. Spaceを再起動

設定後、Spaceを再起動すると自動的にSupabaseに接続されます。

> **Note**: Supabase未設定の場合はSQLiteにフォールバックしますが、HuggingFace Space再起動時にデータは消えます。
