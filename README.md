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

## Persistent Storage Setup

**重要**: データを永続化するには、HuggingFace SpaceのSettingsで「Persistent Storage」を有効にしてください。

1. Space Settings → Repository secrets の下にある「Persistent storage」セクション
2. 「Enable persistent storage」をクリック
3. Spaceを再起動

これにより、登録した機械データと製品画像が Space 再起動後も保持されます。
