// 機械台帳 メインアプリケーション
import { api } from './api.js';
import { showToast, formatDate } from './utils.js';

// デフォルト画像（SVGプレースホルダー）
const DEFAULT_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Crect fill='%23f0f0f0' width='200' height='200'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%23999' font-size='14'%3ENo Image%3C/text%3E%3C/svg%3E";

// 状態
let selectedFile = null;
let selectedEngine = 'google-vision-gemini'; // デフォルト: Google Vision OCR + Gemini（高精度）
let driveConnected = false;
let progressInterval = null;
let localProgressInterval = null;
let editingEquipmentId = null;
let localFiles = [];
let editingSignboardId = null;
let currentPage = 'equipment';
let currentDetailEquipmentId = null;

// 初期化
document.addEventListener('DOMContentLoaded', async () => {
    loadEngines();
    loadEquipment();
    loadConfig();
    setupEventListeners();
    setupModal();
    setupEditModal();
    setupDetailModal();
    setupPageNavigation();
    setupSignboardModal();
    setupDropZone();
    loadVisionConfig();
    setupVisionCredentials();

    // フォルダ情報を先に読み込んでからドライブ状態を確認
    await loadFolderInfo();
    checkDriveStatus();

    // API使用量を読み込み
    loadApiUsage();
});

// モーダル
function setupModal() {
    const modal = document.getElementById('settings-modal');
    document.getElementById('settings-btn').addEventListener('click', () => modal.classList.add('visible'));
    document.getElementById('close-settings').addEventListener('click', () => modal.classList.remove('visible'));
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('visible'); });
}

// 編集モーダル
function setupEditModal() {
    const modal = document.getElementById('edit-modal');
    if (!modal) return;
    document.getElementById('close-edit-modal').addEventListener('click', () => modal.classList.remove('visible'));
    document.getElementById('cancel-edit-btn').addEventListener('click', () => modal.classList.remove('visible'));
    document.getElementById('save-edit-btn').addEventListener('click', saveEquipmentEdit);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('visible'); });
}

// 詳細モーダル
function setupDetailModal() {
    const modal = document.getElementById('equipment-detail-modal');
    if (!modal) return;
    document.getElementById('close-detail-modal').addEventListener('click', () => modal.classList.remove('visible'));
    document.getElementById('detail-edit-btn').addEventListener('click', () => {
        modal.classList.remove('visible');
        editEquipment(currentDetailEquipmentId);
    });
    document.getElementById('detail-delete-btn').addEventListener('click', async () => {
        if (confirm('この機械を削除しますか?')) {
            await deleteEquipment(currentDetailEquipmentId);
            modal.classList.remove('visible');
        }
    });
    document.getElementById('detail-save-notes-btn').addEventListener('click', saveEquipmentNotes);

    // 仕様書検索ボタン
    document.getElementById('search-spec-btn').addEventListener('click', () => searchManual('spec', '仕様書'));

    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('visible'); });

    // 検索結果モーダル
    const searchModal = document.getElementById('search-results-modal');
    document.getElementById('close-search-modal').addEventListener('click', () => searchModal.classList.remove('visible'));
    searchModal.addEventListener('click', (e) => { if (e.target === searchModal) searchModal.classList.remove('visible'); });
}

// Web検索APIで説明書・仕様書を検索
async function searchManual(searchType, displayName) {
    const model = document.getElementById('detail-model').textContent;
    const manufacturer = document.getElementById('detail-manufacturer').textContent;
    const name = document.getElementById('detail-name').textContent;

    // 検索クエリを構築
    let query = '';
    if (model && model !== '-') query += model + ' ';
    if (manufacturer && manufacturer !== '-') query += manufacturer + ' ';
    if (name && name !== '-' && !query.includes(name)) query += name + ' ';
    query = query.trim();

    if (!query) {
        showToast('検索する情報がありません', 'error');
        return;
    }

    // 検索結果モーダルを表示
    const searchModal = document.getElementById('search-results-modal');
    const resultsContainer = document.getElementById('search-results-list');
    const queryInfo = document.getElementById('search-query-info');
    const title = document.getElementById('search-results-title');

    title.textContent = `📚 ${displayName}検索結果`;
    queryInfo.innerHTML = `<strong>検索キーワード:</strong> ${query}`;
    resultsContainer.innerHTML = '<div class="search-loading"><div class="spinner"></div><p>検索中...</p></div>';
    searchModal.classList.add('visible');

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, search_type: searchType })
        });

        if (!response.ok) throw new Error('検索に失敗しました');

        const data = await response.json();

        if (data.results.length === 0) {
            resultsContainer.innerHTML = '<div class="search-empty"><p>検索結果が見つかりませんでした</p></div>';
            return;
        }

        resultsContainer.innerHTML = data.results.map((result, index) => `
            <div class="search-result-item">
                <div class="search-result-number">${index + 1}</div>
                <div class="search-result-content">
                    <a href="${result.url}" target="_blank" class="search-result-title">${escapeHtml(result.title)}</a>
                    <div class="search-result-url">${result.url}</div>
                    <div class="search-result-snippet">${escapeHtml(result.snippet)}</div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = `<div class="search-error"><p>検索に失敗しました: ${error.message}</p></div>`;
    }
}

// HTMLエスケープ
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 機械詳細表示
window.showEquipmentDetail = async function(id) {
    currentDetailEquipmentId = id;
    try {
        const equipment = await api.get(`/api/equipment/${id}`);
        const modal = document.getElementById('equipment-detail-modal');

        document.getElementById('detail-image').src = equipment.image_path || DEFAULT_IMAGE;
        document.getElementById('detail-name').textContent = equipment.equipment_name || '-';
        document.getElementById('detail-model').textContent = equipment.model_number || '-';
        document.getElementById('detail-serial').textContent = equipment.serial_number || '-';
        document.getElementById('detail-manufacturer').textContent = equipment.manufacturer || '-';
        document.getElementById('detail-category').textContent = equipment.tool_category || '-';
        document.getElementById('detail-purchase-date').textContent = equipment.purchase_date || '-';
        document.getElementById('detail-notes').value = equipment.notes || '';

        modal.classList.add('visible');
    } catch (error) {
        showToast('機械情報の読み込みに失敗しました', 'error');
    }
};

// メモ保存
async function saveEquipmentNotes() {
    if (!currentDetailEquipmentId) return;

    const btn = document.getElementById('detail-save-notes-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 保存中...';

    const notes = document.getElementById('detail-notes').value;

    try {
        const response = await fetch(`/api/equipment/${currentDetailEquipmentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: notes })
        });

        if (!response.ok) throw new Error('保存に失敗しました');

        showToast('メモを保存しました');
    } catch (error) {
        showToast('メモの保存に失敗しました', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '💾 メモを保存';
    }
}

// 機械編集
window.editEquipment = async function(id) {
    editingEquipmentId = id;
    try {
        const equipment = await api.get(`/api/equipment/${id}`);
        document.getElementById('edit-equipment-name').value = equipment.equipment_name || '';
        document.getElementById('edit-model-number').value = equipment.model_number || '';
        document.getElementById('edit-serial-number').value = equipment.serial_number || '';
        document.getElementById('edit-purchase-date').value = equipment.purchase_date || '';
        document.getElementById('edit-tool-category').value = equipment.tool_category || '';
        document.getElementById('edit-manufacturer').value = equipment.manufacturer || '';
        document.getElementById('edit-modal').classList.add('visible');
    } catch (error) {
        showToast('機械情報の読み込みに失敗しました', 'error');
    }
};

async function saveEquipmentEdit() {
    if (!editingEquipmentId) return;

    const btn = document.getElementById('save-edit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 保存中...';

    const data = {
        equipment_name: document.getElementById('edit-equipment-name').value,
        model_number: document.getElementById('edit-model-number').value,
        serial_number: document.getElementById('edit-serial-number').value,
        purchase_date: document.getElementById('edit-purchase-date').value,
        tool_category: document.getElementById('edit-tool-category').value,
        manufacturer: document.getElementById('edit-manufacturer').value
    };

    try {
        const response = await fetch(`/api/equipment/${editingEquipmentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error('更新に失敗しました');

        showToast('機械情報を更新しました');
        document.getElementById('edit-modal').classList.remove('visible');
        loadEquipment();
    } catch (error) {
        showToast('更新に失敗しました', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '保存';
        editingEquipmentId = null;
    }
}

// タブ
function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`${tab.dataset.tab}-tab`).classList.add('active');
        });
    });
}

// 設定
async function loadConfig() {
    try {
        const data = await api.get('/api/config');
        const folderIdEl = document.getElementById('current-folder-id');
        const folderInputEl = document.getElementById('folder-id-input');
        const credentialsUploadEl = document.getElementById('credentials-upload');
        const credentialsStatusEl = document.getElementById('credentials-status');

        if (folderIdEl) folderIdEl.textContent = data.google_drive_folder_id || '未設定';
        if (folderInputEl) folderInputEl.value = data.google_drive_folder_id || '';
        if (data.has_credentials && credentialsUploadEl) {
            credentialsUploadEl.classList.add('uploaded');
            if (credentialsStatusEl) credentialsStatusEl.textContent = '✓ credentials.json アップロード済み';
        }
    } catch (error) { console.error('設定の読み込みに失敗:', error); }
}

async function saveFolderId() {
    const folderId = document.getElementById('folder-id-input').value.trim();
    if (!folderId) { showToast('フォルダIDを入力してください', 'error'); return; }
    const formData = new FormData();
    formData.append('folder_id', folderId);
    try {
        const data = await api.post('/api/config', formData);
        if (data.success) {
            showToast('フォルダ設定を保存しました');
            document.getElementById('current-folder-id').textContent = data.config.google_drive_folder_id;
            checkDriveStatus();
        }
    } catch (error) { showToast('保存に失敗しました', 'error'); }
}

async function uploadCredentials(file) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const data = await api.post('/api/config/credentials', formData);
        if (data.success) {
            showToast('認証情報を保存しました');
            document.getElementById('credentials-upload').classList.add('uploaded');
            document.getElementById('credentials-status').textContent = '✓ credentials.json アップロード済み';
            checkDriveStatus();
        }
    } catch (error) { showToast('アップロードに失敗しました', 'error'); }
}

// Google Vision API設定
async function loadVisionConfig() {
    try {
        const data = await api.get('/api/config/vision');
        const statusDot = document.getElementById('vision-status-dot');
        const statusText = document.getElementById('vision-status-text');
        const accountInfo = document.getElementById('vision-account-info');
        const uploadArea = document.getElementById('vision-credentials-upload');
        const uploadStatus = document.getElementById('vision-credentials-status');

        if (data.configured) {
            statusDot.classList.add('connected');
            statusText.textContent = `設定済み (${data.source || 'ローカル'})`;
            accountInfo.style.display = 'block';
            document.getElementById('vision-client-email').textContent = data.client_email || '-';
            document.getElementById('vision-project-id').textContent = data.project_id || '-';
            uploadArea.classList.add('uploaded');
            uploadStatus.textContent = '✓ サービスアカウントキー設定済み';
        } else {
            statusDot.classList.remove('connected');
            statusText.textContent = '未設定';
            accountInfo.style.display = 'none';
            uploadArea.classList.remove('uploaded');
            uploadStatus.textContent = 'クリックしてサービスアカウントキーをアップロード';
        }
    } catch (error) {
        console.error('Vision設定の読み込みに失敗:', error);
        document.getElementById('vision-status-text').textContent = '読み込み失敗';
    }
}

function setupVisionCredentials() {
    const uploadArea = document.getElementById('vision-credentials-upload');
    const fileInput = document.getElementById('vision-credentials-input');

    if (!uploadArea || !fileInput) return;

    uploadArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            await uploadVisionCredentials(e.target.files[0]);
        }
    });
}

async function uploadVisionCredentials(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/config/vision/credentials', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'アップロードに失敗しました');
        }

        showToast('Vision API認証情報を保存しました');
        loadVisionConfig();
        loadEngines(); // エンジンリストを更新
    } catch (error) {
        showToast(error.message || 'アップロードに失敗しました', 'error');
    }
}

// 処理エンジン（LLMエンジンのみ）
async function loadEngines() {
    try {
        const container = document.getElementById('engine-selector');
        if (!container) return;

        // APIからLLMエンジン一覧を取得
        const data = await api.get('/api/llm-engines');
        const engines = data.engines || [];

        container.innerHTML = engines.map(engine => `
            <div class="engine-option ${engine.id === selectedEngine ? 'selected' : ''} ${!engine.available ? 'disabled' : ''}"
                 data-engine="${engine.id}">
                <h3>${engine.name}</h3>
                <p>${engine.description}</p>
            </div>
        `).join('');

        container.querySelectorAll('.engine-option').forEach(option => {
            option.addEventListener('click', () => {
                if (option.classList.contains('disabled')) return;
                container.querySelectorAll('.engine-option').forEach(o => o.classList.remove('selected'));
                option.classList.add('selected');
                selectedEngine = option.dataset.engine;
            });
        });
    } catch (error) { console.error('エンジンの読み込みに失敗:', error); }
}

// Google ドライブ
async function checkDriveStatus() {
    const indicator = document.getElementById('drive-status-indicator');
    const statusText = document.getElementById('drive-status-text');
    const modalDot = document.getElementById('modal-status-dot');
    const modalText = document.getElementById('modal-status-text');
    const loadBtn = document.getElementById('load-drive-files-btn');
    const processBtn = document.getElementById('process-all-btn');

    if (statusText) statusText.textContent = 'Google ドライブに接続中...';

    try {
        // 実際にファイル一覧を取得して接続確認
        const data = await api.get('/api/google-drive/equipment-images');
        const connected = data.files !== undefined;
        const fileCount = data.files ? data.files.length : 0;

        if (connected) {
            if (indicator) indicator.classList.add('connected');
            if (statusText) statusText.textContent = `Google ドライブ接続済み（${fileCount}件のファイル）`;
            if (modalDot) modalDot.classList.add('connected');
            if (modalText) modalText.textContent = '接続済み';
            driveConnected = true;
            if (loadBtn) loadBtn.disabled = false;
            if (processBtn) processBtn.disabled = fileCount === 0;

            // ファイルがある場合は自動的にファイル一覧を表示
            if (fileCount > 0) {
                displayDriveFiles(data.files);
            } else {
                const container = document.getElementById('drive-files');
                container.style.display = 'block';
                container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">📂 フォルダにファイルがありません<br><small>Google Driveの指定フォルダを確認してください</small></p>';
            }
        }
    } catch (error) {
        console.error('Drive status check error:', error);
        if (indicator) indicator.classList.remove('connected');
        if (statusText) statusText.textContent = `Google ドライブ接続エラー: ${error.message || '接続失敗'}`;
        if (modalDot) modalDot.classList.remove('connected');
        if (modalText) modalText.textContent = '未接続';
        driveConnected = false;
        // ファイル読込ボタンは常に有効（ユーザーが手動で試せるように）
        if (loadBtn) loadBtn.disabled = false;
        if (processBtn) processBtn.disabled = true;
    }
}

// フォルダ情報を保持
let folderInfo = null;

// フォルダ情報を取得
async function loadFolderInfo() {
    try {
        folderInfo = await api.get('/api/google-drive/folder-info');
        console.log('Folder info:', folderInfo);
    } catch (error) {
        console.error('Failed to load folder info:', error);
    }
}

// ファイル一覧を表示する共通関数
function displayDriveFiles(files) {
    const container = document.getElementById('drive-files');
    const processBtn = document.getElementById('process-all-btn');
    container.style.display = 'block';

    // フォルダリンクを生成
    let folderLinks = '';
    if (folderInfo && folderInfo.equipment_folder_urls) {
        folderLinks = folderInfo.equipment_folder_urls.map((url, i) =>
            `<a href="${url}" target="_blank" style="color: var(--primary); text-decoration: underline;">フォルダ${i + 1}</a>`
        ).join(' | ');
    }

    if (files.length === 0) {
        container.innerHTML = `
            <div style="padding: 16px; background: var(--bg-secondary); border-radius: 8px; text-align: center;">
                <p style="color: var(--text-muted); margin-bottom: 12px;">📂 フォルダにファイルがありません</p>
                ${folderLinks ? `<p style="font-size: 0.85rem;">確認先: ${folderLinks}</p>` : ''}
                <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">
                    ※ 上記フォルダに画像をアップロードしてから「ファイル読込」を押してください
                </p>
            </div>
        `;
        if (processBtn) processBtn.disabled = true;
        return;
    }

    container.innerHTML = `
        <div style="padding: 8px 12px; background: var(--bg-secondary); border-radius: 8px; margin-bottom: 12px;">
            <strong>📁 ${files.length}件のファイル</strong>
            ${folderLinks ? `<span style="font-size: 0.85rem; margin-left: 12px;">${folderLinks}</span>` : ''}
        </div>
        ${files.map(file => `
            <div class="drive-file">
                <a href="${file.image_url}" target="_blank" title="クリックで画像を開く" style="cursor: pointer;">
                    <img src="${file.thumbnail_url}" alt="" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px; margin-right: 8px; transition: transform 0.2s;" onerror="this.style.display='none'" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'">
                </a>
                <span class="drive-file-name" style="flex: 1;">${file.name}</span>
                <button class="btn btn-primary btn-sm" onclick="processSingleFile('${file.id}', '${file.name.replace(/'/g, "\\'")}')">処理</button>
            </div>
        `).join('')}
    `;
    if (processBtn) processBtn.disabled = false;
}

async function connectGoogleDrive() {
    // 設定モーダル内のフォルダIDがあれば先に保存
    const folderInput = document.getElementById('folder-id-input');
    if (folderInput && folderInput.value.trim()) {
        const formData = new FormData();
        formData.append('folder_id', folderInput.value.trim());
        try {
            const configData = await api.post('/api/config', formData);
            if (configData.success) {
                document.getElementById('current-folder-id').textContent = configData.config.google_drive_folder_id;
            }
        } catch (e) { /* ignore */ }
    }

    const btn = document.getElementById('connect-drive-btn');
    const settingsBtn = document.getElementById('settings-connect-drive-btn');
    const activeBtn = btn || settingsBtn;
    if (activeBtn) {
        activeBtn.disabled = true;
        activeBtn.innerHTML = '<span class="spinner-small"></span> 接続中...';
    }
    try {
        const data = await api.post('/api/google-drive/connect');
        if (data.success) { showToast('Google ドライブに接続しました'); checkDriveStatus(); }
    } catch (error) { showToast('接続に失敗しました', 'error'); }
    finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🔗 接続'; }
        if (settingsBtn) { settingsBtn.disabled = false; settingsBtn.innerHTML = '🔗 接続'; }
    }
}

async function loadDriveFiles() {
    const container = document.getElementById('drive-files');
    const processBtn = document.getElementById('process-all-btn');
    container.style.display = 'block';
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        showToast('ファイル一覧を取得中...');
        const data = await api.get('/api/google-drive/equipment-images');
        displayDriveFiles(data.files || []);
        if (data.files && data.files.length > 0) {
            showToast(`${data.files.length}件のファイルを読み込みました`);
        }
    } catch (error) {
        console.error('loadDriveFiles error:', error);
        container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 20px;">ファイルの読み込みに失敗しました<br><small>${error.message || 'エラー'}</small></p>`;
        if (processBtn) processBtn.disabled = true;
    }
}

window.processSingleFile = async function(fileId, fileName) {
    showToast(`${fileName} を処理中...`);
    const formData = new FormData();
    formData.append('llm_engine', selectedEngine);
    try {
        const response = await fetch(`/api/google-drive/process/${fileId}`, { method: 'POST', body: formData });
        if (response.ok) {
            const data = await response.json();
            showToast(`${fileName} を処理しました`);
            loadEquipment();
            loadApiUsage(); // 使用量を更新

            // OCR結果モーダルを表示
            if (data.equipment) {
                showOcrResultModal(fileId, fileName, data.equipment);
            }
        } else {
            // エラー詳細を取得
            const errorData = await response.json().catch(() => ({}));
            const errorMsg = errorData.detail || `HTTPエラー ${response.status}`;
            console.error('Process error:', errorMsg);
            showToast(`${fileName} の処理に失敗: ${errorMsg}`, 'error');
        }
    } catch (error) {
        console.error('Process exception:', error);
        showToast(`${fileName} の処理に失敗: ${error.message}`, 'error');
    }
};

// OCR結果モーダルを表示
function showOcrResultModal(fileId, fileName, equipment) {
    const modal = document.getElementById('ocr-result-modal');
    const imageEl = document.getElementById('ocr-result-image');
    const rawTextEl = document.getElementById('ocr-raw-text');
    const extractedInfoEl = document.getElementById('ocr-extracted-info');

    // 画像を設定
    imageEl.src = `/api/google-drive/image/${fileId}`;
    imageEl.alt = fileName;

    // OCRテキストを表示
    const rawText = equipment.raw_text || '(テキストが読み取れませんでした)';
    rawTextEl.textContent = rawText;

    // 抽出結果を表示
    const fields = [
        { key: 'equipment_name', label: '機械名' },
        { key: 'manufacturer', label: 'メーカー' },
        { key: 'model_number', label: '型番' },
        { key: 'serial_number', label: 'シリアル番号' },
        { key: 'weight', label: '重量' },
        { key: 'output_power', label: '出力' },
        { key: 'engine_model', label: 'エンジン型式' },
        { key: 'year_manufactured', label: '製造年' }
    ];

    extractedInfoEl.innerHTML = fields.map(f => {
        const value = equipment[f.key] || '-';
        return `
            <div style="background: var(--bg-secondary); padding: 8px 12px; border-radius: 6px;">
                <div style="font-size: 0.75rem; color: var(--text-muted);">${f.label}</div>
                <div style="font-weight: 600;">${value}</div>
            </div>
        `;
    }).join('');

    modal.classList.add('visible');
}

// OCR結果モーダルを閉じる
function closeOcrResultModal() {
    document.getElementById('ocr-result-modal').classList.remove('visible');
}

// JSON読み込みモーダル
function openJsonImportModal() {
    document.getElementById('json-import-modal').classList.add('visible');
    document.getElementById('json-paste-input').value = '';
    document.getElementById('json-file-input').value = '';
    document.getElementById('json-import-result').style.display = 'none';
    loadJsonFolderFiles();
}

// フォルダ内のJSONファイル一覧を読み込み
async function loadJsonFolderFiles() {
    const container = document.getElementById('json-folder-files');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const data = await api.get('/api/json-import/files');

        if (data.files.length === 0) {
            container.innerHTML = `
                <p style="color: var(--text-muted); text-align: center; margin: 0;">
                    JSONファイルがありません<br>
                    <small>${data.folder}</small>
                </p>
            `;
            return;
        }

        container.innerHTML = data.files.map(file => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px; border-bottom: 1px solid var(--border);">
                <div>
                    <div style="font-weight: 600;">${file.name}</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">
                        ${file.equipment_count}件の機械データ
                    </div>
                </div>
                <button class="btn btn-primary btn-sm" onclick="importJsonFromFolder('${file.name}')">読み込み</button>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger);">読み込みエラー: ${error.message}</p>`;
    }
}

// フォルダからJSONをインポート
window.importJsonFromFolder = async function(filename) {
    const resultDiv = document.getElementById('json-import-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const response = await fetch(`/api/json-import/import/${encodeURIComponent(filename)}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (response.ok && data.success) {
            resultDiv.innerHTML = `
                <p style="color: var(--success);">✓ ${data.imported_count}件の機械を読み込みました（${filename}）</p>
            `;
            loadEquipment();
            loadJsonFolderFiles(); // リストを更新
        } else {
            resultDiv.innerHTML = `<p style="color: var(--danger);">エラー: ${data.detail || '読み込み失敗'}</p>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<p style="color: var(--danger);">エラー: ${error.message}</p>`;
    }
};

function closeJsonImportModal() {
    document.getElementById('json-import-modal').classList.remove('visible');
}

// JSON一括インポート（data/json-importフォルダから）
async function importAllJsonFiles() {
    if (!confirm('json-importフォルダのJSONファイルをインポートしますか？')) {
        return;
    }

    const btn = document.getElementById('import-all-json-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> インポート中...';

    try {
        const response = await fetch('/api/json-import/import-all', {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('インポートに失敗しました');
        }

        const data = await response.json();

        if (data.success) {
            showToast(`${data.imported}件の機械をインポートしました`);
            loadEquipment();
        } else {
            showToast(data.message || 'インポートに失敗しました', 'error');
        }
    } catch (error) {
        showToast('インポートに失敗しました', 'error');
        console.error('Import error:', error);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '📥 一括インポート';
    }
}

async function submitJsonImport() {
    const fileInput = document.getElementById('json-file-input');
    const pasteInput = document.getElementById('json-paste-input');
    const resultDiv = document.getElementById('json-import-result');

    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        let response;

        if (fileInput.files.length > 0) {
            // ファイルアップロード
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            response = await fetch('/api/equipment/import-json-file', {
                method: 'POST',
                body: formData
            });
        } else if (pasteInput.value.trim()) {
            // JSON貼り付け
            const jsonData = JSON.parse(pasteInput.value);
            // 配列の場合は { equipment: [...] } 形式に変換
            const payload = Array.isArray(jsonData)
                ? { equipment: jsonData }
                : (jsonData.equipment ? jsonData : { equipment: [jsonData] });

            response = await fetch('/api/equipment/import-json', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            resultDiv.innerHTML = '<p style="color: var(--danger);">JSONファイルを選択するか、JSONを貼り付けてください。</p>';
            return;
        }

        const data = await response.json();

        if (response.ok && data.success) {
            resultDiv.innerHTML = `
                <p style="color: var(--success);">✓ ${data.imported_count}件の機械を読み込みました</p>
                ${data.errors.length > 0 ? `<p style="color: var(--warning);">⚠ ${data.errors.length}件のエラー</p>` : ''}
            `;
            loadEquipment();
            setTimeout(() => closeJsonImportModal(), 2000);
        } else {
            resultDiv.innerHTML = `<p style="color: var(--danger);">エラー: ${data.detail || '読み込み失敗'}</p>`;
        }
    } catch (error) {
        console.error('JSON import error:', error);
        resultDiv.innerHTML = `<p style="color: var(--danger);">エラー: ${error.message}</p>`;
    }
}

async function pollProgress() {
    try {
        const data = await api.get('/api/google-drive/progress');
        const progressBar = document.getElementById('progress-bar');
        const progressCount = document.getElementById('progress-count');
        const currentFileName = document.getElementById('current-file-name');
        const currentFileInfo = document.getElementById('current-file-info');
        const progressErrors = document.getElementById('progress-errors');

        if (data.status === 'processing') {
            const percent = data.total > 0 ? (data.current / data.total * 100) : 0;
            progressBar.style.width = `${percent}%`;
            progressCount.textContent = `${data.current} / ${data.total}`;
            currentFileName.textContent = data.current_file || '処理中...';
            if (data.errors?.length > 0) {
                progressErrors.style.display = 'block';
                progressErrors.innerHTML = data.errors.map(e => `<div>✕ ${e.file}: ${e.error}</div>`).join('');
            }
        } else if (data.status === 'complete') {
            progressBar.style.width = '100%';
            progressCount.textContent = `${data.total} / ${data.total}`;
            currentFileInfo.innerHTML = '<span style="color: var(--success); font-weight: 600;">✓ 完了!</span>';
            if (data.errors?.length > 0) {
                progressErrors.style.display = 'block';
                progressErrors.innerHTML = data.errors.map(e => `<div>✕ ${e.file}: ${e.error}</div>`).join('');
            }
            if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
        }
    } catch (error) { console.error('進捗確認エラー:', error); }
}

async function processAllDriveFiles() {
    const btn = document.getElementById('process-all-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressCount = document.getElementById('progress-count');
    const currentFileInfo = document.getElementById('current-file-info');
    const progressErrors = document.getElementById('progress-errors');

    // 処理開始を即座に表示
    showToast('処理を開始しています...');
    console.log('processAllDriveFiles: 処理開始');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 処理中...';
    progressContainer.classList.add('visible');
    progressBar.style.width = '0%';
    progressCount.textContent = '0 / 0';
    currentFileInfo.innerHTML = '<span class="spinner-small"></span><span id="current-file-name">準備中...</span>';
    progressErrors.style.display = 'none';

    // 進捗表示が見えるようにスクロール
    progressContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    progressInterval = setInterval(pollProgress, 500);
    const formData = new FormData();
    formData.append('llm_engine', selectedEngine);

    try {
        console.log('processAllDriveFiles: API呼び出し中...');
        const data = await api.post('/api/google-drive/equipment-images/process-all', formData);
        console.log('processAllDriveFiles: API応答', data);
        await pollProgress();
        if (data.success) {
            if (data.processed_count === 0) {
                showToast('処理するファイルがありませんでした');
            } else {
                showToast(`${data.processed_count}件の機械を処理しました`);
            }
            loadEquipment();
            loadApiUsage(); // 使用量を更新
        } else {
            showToast('処理が完了しましたが、エラーがあります', 'error');
            loadApiUsage(); // エラー時も使用量を更新
        }
    } catch (error) {
        console.error('processAllDriveFiles: エラー', error);
        showToast(`処理に失敗しました: ${error.message || 'サーバーエラー'}`, 'error');
    }
    finally {
        if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
        btn.disabled = false;
        btn.innerHTML = '⚡ 全て処理';
        setTimeout(() => progressContainer.classList.remove('visible'), 3000);
    }
}

// ファイルアップロード
function setupDropZone() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    // 要素が存在しない場合はスキップ
    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]); });
    fileInput.addEventListener('change', (e) => { if (e.target.files.length > 0) handleFileSelect(e.target.files[0]); });
}

function handleFileSelect(file) {
    if (!file.type.startsWith('image/')) { showToast('画像ファイルを選択してください', 'error'); return; }
    selectedFile = file;
    document.getElementById('drop-zone').innerHTML = `<div class="drop-zone-icon">✓</div><p><strong>${file.name}</strong><br>処理の準備ができました</p>`;
    document.getElementById('upload-btn').disabled = false;
}

async function uploadEquipment() {
    if (!selectedFile) return;
    const btn = document.getElementById('upload-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 処理中...';
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('llm_engine', selectedEngine);
    try {
        const response = await fetch('/api/equipment/upload', { method: 'POST', body: formData });
        if (!response.ok) throw new Error('アップロードに失敗しました');
        showToast('機械を登録しました!');
        loadEquipment();
        resetDropZone();
    } catch (error) { showToast('処理に失敗しました', 'error'); }
    finally {
        btn.disabled = false;
        btn.innerHTML = '📥 機械を登録';
    }
}

function resetDropZone() {
    selectedFile = null;
    document.getElementById('drop-zone').innerHTML = `<div class="drop-zone-icon">🏭</div><p>機械の銘板写真をドラッグ＆ドロップ<br>または<strong>クリックして選択</strong></p>`;
    document.getElementById('upload-btn').disabled = true;
    document.getElementById('file-input').value = '';
}

// 機械一覧
async function loadEquipment() {
    const container = document.getElementById('equipment-list');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const data = await api.get('/api/equipment');
        document.getElementById('equipment-count').textContent = data.equipment.length;
        updateEquipmentSummary(data.equipment);
        if (data.equipment.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🏭</div><p>機械が登録されていません</p></div>`;
            return;
        }
        // グリッド表示（看板と同様）
        container.innerHTML = `
            <div class="equipment-grid">
                ${data.equipment.map(renderEquipmentCard).join('')}
            </div>`;
    } catch (error) { container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>機械の読み込みに失敗しました</p></div>`; }
}

function renderEquipmentCard(equipment) {
    const imagePath = equipment.image_path || DEFAULT_IMAGE;
    const categoryBadge = equipment.tool_category
        ? `<span class="category-badge">${equipment.tool_category}</span>`
        : '';
    const serialDisplay = equipment.serial_number
        ? `<div class="equipment-serial">S/N: ${equipment.serial_number}</div>`
        : `<div class="equipment-serial empty">S/N: 未登録</div>`;

    return `
        <div class="equipment-card" onclick="showEquipmentDetail(${equipment.id})" style="cursor: pointer;">
            <div class="equipment-image">
                <img src="${imagePath}" alt="${equipment.equipment_name || ''}" onerror="this.style.display='none'">
                ${categoryBadge}
            </div>
            <div class="equipment-info">
                <div class="equipment-name">${equipment.equipment_name || '-'}</div>
                ${serialDisplay}
                <div class="equipment-model">${equipment.model_number || ''}</div>
            </div>
        </div>`;
}

function updateEquipmentSummary(equipmentList) {
    const total = equipmentList.reduce((sum, eq) => sum + (eq.quantity || 0), 0);
    const summaryEl = document.getElementById('equipment-total');
    if (summaryEl) summaryEl.textContent = total;
}

window.incrementEquipment = async function(id) {
    try {
        const response = await fetch(`/api/equipment/${id}/increment`, { method: 'POST' });
        if (!response.ok) throw new Error('更新失敗');
        const data = await response.json();
        const qtyEl = document.getElementById(`eq-qty-${id}`);
        if (qtyEl) qtyEl.textContent = data.equipment.quantity;
        const card = qtyEl.closest('.equipment-card');
        if (card) {
            const minusBtn = card.querySelector('.qty-btn.minus');
            if (minusBtn) minusBtn.disabled = false;
        }
    } catch (error) {
        showToast('更新に失敗しました', 'error');
    }
};

window.decrementEquipment = async function(id) {
    try {
        const response = await fetch(`/api/equipment/${id}/decrement`, { method: 'POST' });
        if (!response.ok) throw new Error('更新失敗');
        const data = await response.json();
        const qtyEl = document.getElementById(`eq-qty-${id}`);
        if (qtyEl) qtyEl.textContent = data.equipment.quantity;
        const card = qtyEl.closest('.equipment-card');
        if (card) {
            const minusBtn = card.querySelector('.qty-btn.minus');
            if (minusBtn) minusBtn.disabled = data.equipment.quantity === 0;
        }
    } catch (error) {
        showToast('更新に失敗しました', 'error');
    }
};

function renderEquipmentRow(equipment) {
    const categoryBadge = equipment.tool_category
        ? `<span class="category-badge">${equipment.tool_category}</span>`
        : '-';
    // AI補完可能かどうか（raw_textがあり、llm_engineがまだない場合）
    const canEnhance = equipment.raw_text && !equipment.raw_text.startsWith('(Gemini') && !equipment.llm_engine;

    return `
        <tr>
            <td class="filename-cell" title="${equipment.file_name || ''}">${equipment.file_name || '-'}</td>
            <td><strong>${equipment.equipment_name || '-'}</strong></td>
            <td>${equipment.model_number || '-'}</td>
            <td>${equipment.serial_number || '-'}</td>
            <td>${equipment.purchase_date || '-'}</td>
            <td>${categoryBadge}</td>
            <td class="action-cell">${equipment.model_number ? `<button class="btn-icon-sm spec" onclick="searchSpecSheet(${equipment.id})" title="仕様書を検索">📄</button>` : '-'}</td>
            <td class="action-cell">${canEnhance ? `<button class="btn-icon-sm ai" onclick="enhanceWithAI(${equipment.id})" title="AI補完">🤖</button>` : '-'}</td>
            <td class="action-cell"><button class="btn-icon-sm" onclick="editEquipment(${equipment.id})" title="編集">✏️</button></td>
            <td class="action-cell"><button class="btn-icon-sm danger" onclick="deleteEquipment(${equipment.id})" title="削除">🗑️</button></td>
        </tr>`;
}

// 仕様書検索
window.searchSpecSheet = async function(equipmentId) {
    showToast('仕様書を検索中...');

    try {
        const response = await fetch(`/api/equipment/${equipmentId}/spec-search`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || '検索に失敗しました');
        }

        if (data.results && data.results.length > 0) {
            showSpecResults(data.results, data.query);
        } else {
            showToast('仕様書が見つかりませんでした', 'error');
        }
    } catch (error) {
        showToast(error.message || '検索に失敗しました', 'error');
    }
};

function showSpecResults(results, query) {
    // 既存のモーダルがあれば削除
    const existingModal = document.getElementById('spec-results-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'spec-results-modal';
    modal.className = 'modal-overlay visible';
    modal.innerHTML = `
        <div class="modal" style="max-width: 600px;">
            <div class="modal-header">
                <div class="modal-title">📄 仕様書検索結果</div>
                <button class="modal-close" onclick="closeSpecModal()">&times;</button>
            </div>
            <div class="modal-body">
                <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
                    検索: "${query}"
                </p>
                <div class="spec-results-list">
                    ${results.map((r, i) => `
                        <div class="spec-result-item" onclick="window.open('${r.url}', '_blank')">
                            <div class="spec-result-title">
                                ${r.url.toLowerCase().includes('.pdf') ? '📕' : '🔗'}
                                ${escapeHtmlForDisplay(r.title)}
                            </div>
                            <div class="spec-result-url">${escapeHtmlForDisplay(r.url)}</div>
                            <div class="spec-result-snippet">${escapeHtmlForDisplay(r.snippet)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeSpecModal();
    });
}

function escapeHtmlForDisplay(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

window.closeSpecModal = function() {
    const modal = document.getElementById('spec-results-modal');
    if (modal) modal.remove();
};

window.deleteEquipment = async function(id) {
    if (!confirm('この機械を削除しますか?')) return;
    try { await api.delete(`/api/equipment/${id}`); showToast('機械を削除しました'); loadEquipment(); }
    catch (error) { showToast('削除に失敗しました', 'error'); }
};

window.enhanceWithAI = async function(id) {
    showToast('AI補完を実行中...');
    try {
        const response = await fetch(`/api/equipment/${id}/enhance`, {
            method: 'POST'
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'AI補完に失敗しました');
        }

        if (data.enhanced_fields && data.enhanced_fields.length > 0) {
            showToast(`AI補完完了: ${data.enhanced_fields.length}項目を補完しました`);
        } else {
            showToast('新しい情報は見つかりませんでした');
        }
        loadEquipment();
    } catch (error) {
        showToast(error.message || 'AI補完に失敗しました', 'error');
    }
};

async function clearAllEquipment() {
    if (!confirm('全ての機械を削除しますか?')) return;
    try { await api.delete('/api/equipment'); showToast('全ての機械を削除しました'); loadEquipment(); }
    catch (error) { showToast('削除に失敗しました', 'error'); }
}

// API使用量の読み込み
async function loadApiUsage() {
    try {
        const data = await api.get('/api/config/api-usage');
        const countEl = document.getElementById('api-usage-count');
        const barEl = document.getElementById('api-usage-bar');

        if (countEl && barEl) {
            const usage = data.usage_count || 0;
            const limit = data.free_limit || 1000;
            const remaining = data.remaining || (limit - usage);
            const percentage = Math.min(100, (usage / limit) * 100);

            countEl.textContent = `${usage} / ${limit} (残り ${remaining})`;
            barEl.style.width = `${percentage}%`;

            // 80%以上使用で警告色
            if (percentage >= 80) {
                barEl.style.background = 'var(--danger)';
            } else if (percentage >= 50) {
                barEl.style.background = 'var(--warning)';
            } else {
                barEl.style.background = 'var(--success)';
            }
        }
    } catch (error) {
        console.error('API使用量の取得に失敗:', error);
        const countEl = document.getElementById('api-usage-count');
        if (countEl) countEl.textContent = '取得失敗';
    }
}

// APIテスト（Gemini + Vision）
async function testGeminiApi() {
    const btn = document.getElementById('test-api-btn');
    const resultDiv = document.getElementById('api-test-result');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> テスト中...';
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    let html = '';

    // 1. Test Vision API
    try {
        const visionResponse = await fetch('/api/config/test-vision');
        const visionData = await visionResponse.json();

        html += '<h4 style="margin: 0 0 12px 0;">📷 Cloud Vision API テスト</h4>';

        if (visionData.service_account_configured) {
            html += `<p>✓ サービスアカウント: ${visionData.client_email}</p>`;
            html += `<p>✓ プロジェクト: ${visionData.project_id}</p>`;
        } else {
            html += `<p style="color: var(--danger);">✗ サービスアカウント未設定</p>`;
        }

        if (visionData.api_enabled) {
            html += `<p style="color: var(--success);"><strong>✓ Cloud Vision API: 有効</strong></p>`;
        } else if (visionData.error) {
            html += `<p style="color: var(--danger);"><strong>✗ ${visionData.error}</strong></p>`;
            if (visionData.enable_url) {
                html += `<p><a href="${visionData.enable_url}" target="_blank" style="color: var(--primary);">→ APIを有効化する</a></p>`;
            }
        }

        html += '<hr style="margin: 12px 0; border: none; border-top: 1px solid var(--border);">';
    } catch (error) {
        html += `<p style="color: var(--danger);">Vision APIテストに失敗: ${error.message}</p>`;
    }

    // 2. Test Gemini API
    try {
        const response = await fetch('/api/config/test-gemini');
        const data = await response.json();

        html += '<h4 style="margin: 0 0 12px 0;">🤖 Gemini API テスト</h4>';
        html += `<p><strong>APIキー:</strong> ${data.api_key_prefix || '未設定'}</p>`;

        if (data.test_result) {
            if (data.test_result.success) {
                html += `<p style="color: var(--success);"><strong>✓ テスト成功!</strong> (${data.test_result.model})</p>`;
            } else {
                html += `<p style="color: var(--danger);"><strong>✗ テスト失敗:</strong> ${data.test_result.error}</p>`;
            }
        }
    } catch (error) {
        html += `<p style="color: var(--danger);">Gemini APIテストに失敗: ${error.message}</p>`;
    }

    resultDiv.innerHTML = html;
    btn.disabled = false;
    btn.innerHTML = '🔧 APIテスト';
}

// イベントリスナー
function setupEventListeners() {
    document.getElementById('refresh-btn').addEventListener('click', loadEquipment);
    document.getElementById('clear-all-btn').addEventListener('click', clearAllEquipment);
    document.getElementById('load-drive-files-btn').addEventListener('click', loadDriveFiles);
    document.getElementById('process-all-btn').addEventListener('click', processAllDriveFiles);

    // APIテストボタン
    const testApiBtn = document.getElementById('test-api-btn');
    if (testApiBtn) {
        testApiBtn.addEventListener('click', testGeminiApi);
    }

    // OCR結果モーダル
    const closeOcrBtn = document.getElementById('close-ocr-modal');
    if (closeOcrBtn) {
        closeOcrBtn.addEventListener('click', closeOcrResultModal);
    }
    const ocrModal = document.getElementById('ocr-result-modal');
    if (ocrModal) {
        ocrModal.addEventListener('click', (e) => {
            if (e.target === ocrModal) closeOcrResultModal();
        });
    }

    // JSON読み込みモーダル
    const importJsonBtn = document.getElementById('import-json-btn');
    if (importJsonBtn) {
        importJsonBtn.addEventListener('click', openJsonImportModal);
    }

    // JSON一括インポート
    const importAllJsonBtn = document.getElementById('import-all-json-btn');
    if (importAllJsonBtn) {
        importAllJsonBtn.addEventListener('click', importAllJsonFiles);
    }
    const closeJsonImportBtn = document.getElementById('close-json-import-modal');
    if (closeJsonImportBtn) {
        closeJsonImportBtn.addEventListener('click', closeJsonImportModal);
    }
    const cancelJsonImportBtn = document.getElementById('cancel-json-import');
    if (cancelJsonImportBtn) {
        cancelJsonImportBtn.addEventListener('click', closeJsonImportModal);
    }
    const submitJsonImportBtn = document.getElementById('submit-json-import');
    if (submitJsonImportBtn) {
        submitJsonImportBtn.addEventListener('click', submitJsonImport);
    }
    const jsonImportModal = document.getElementById('json-import-modal');
    if (jsonImportModal) {
        jsonImportModal.addEventListener('click', (e) => {
            if (e.target === jsonImportModal) closeJsonImportModal();
        });
    }

    // 設定セクションの開閉
    document.querySelectorAll('.settings-section-header').forEach(header => {
        header.addEventListener('click', () => {
            const section = header.parentElement;
            section.classList.toggle('collapsed');
        });
    });
}

// ローカルフォルダ機能
async function loadLocalFolderInfo() {
    try {
        const data = await api.get('/api/local-files');
        document.getElementById('local-folder-path').textContent = data.folder;
    } catch (error) {
        document.getElementById('local-folder-path').textContent = '取得失敗';
    }
}

async function loadLocalFiles() {
    const container = document.getElementById('local-files');
    const processBtn = document.getElementById('process-local-all-btn');
    container.style.display = 'block';
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const data = await api.get('/api/local-files');
        localFiles = data.files;

        if (data.files.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">画像ファイルが見つかりません<br><small>data/images フォルダに画像を配置してください</small></p>';
            processBtn.disabled = true;
            return;
        }

        container.innerHTML = data.files.map(file => `
            <div class="drive-file">
                <span class="drive-file-name">📄 ${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
                <button class="btn btn-primary btn-sm" onclick="processLocalFile('${file.name.replace(/'/g, "\\'")}')">処理</button>
            </div>
        `).join('');

        processBtn.disabled = false;
        showToast(`${data.files.length}件のファイルを読み込みました`);
    } catch (error) {
        container.innerHTML = '<p style="color: var(--danger); text-align: center; padding: 20px;">ファイルの読み込みに失敗しました</p>';
        processBtn.disabled = true;
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

window.processLocalFile = async function(filename) {
    showToast(`${filename} を処理中...`);
    const formData = new FormData();
    formData.append('filename', filename);
    formData.append('llm_engine', selectedEngine);

    try {
        const response = await fetch('/api/local-files/process', {
            method: 'POST',
            body: formData
        });
        if (response.ok) {
            showToast(`${filename} を処理しました`);
            loadEquipment();
        } else {
            throw new Error('処理に失敗しました');
        }
    } catch (error) {
        showToast(`${filename} の処理に失敗しました`, 'error');
    }
};

async function pollLocalProgress() {
    try {
        const data = await api.get('/api/local-files/progress');
        const progressBar = document.getElementById('local-progress-bar');
        const progressCount = document.getElementById('local-progress-count');
        const currentFileName = document.getElementById('local-current-file-name');
        const currentFileInfo = document.getElementById('local-current-file-info');
        const progressErrors = document.getElementById('local-progress-errors');

        if (data.status === 'processing') {
            const percent = data.total > 0 ? (data.current / data.total * 100) : 0;
            progressBar.style.width = `${percent}%`;
            progressCount.textContent = `${data.current} / ${data.total}`;
            currentFileName.textContent = data.current_file || '処理中...';
            if (data.errors?.length > 0) {
                progressErrors.style.display = 'block';
                progressErrors.innerHTML = data.errors.map(e => `<div>✕ ${e.file}: ${e.error}</div>`).join('');
            }
        } else if (data.status === 'completed') {
            progressBar.style.width = '100%';
            progressCount.textContent = `${data.total} / ${data.total}`;
            currentFileInfo.innerHTML = '<span style="color: var(--success); font-weight: 600;">✓ 完了!</span>';
            if (data.errors?.length > 0) {
                progressErrors.style.display = 'block';
                progressErrors.innerHTML = data.errors.map(e => `<div>✕ ${e.file}: ${e.error}</div>`).join('');
            }
            if (localProgressInterval) {
                clearInterval(localProgressInterval);
                localProgressInterval = null;
            }
            loadEquipment();
        }
    } catch (error) {
        console.error('進捗確認エラー:', error);
    }
}

async function processAllLocalFiles() {
    const btn = document.getElementById('process-local-all-btn');
    const progressContainer = document.getElementById('local-progress-container');
    const progressBar = document.getElementById('local-progress-bar');
    const progressCount = document.getElementById('local-progress-count');
    const currentFileInfo = document.getElementById('local-current-file-info');
    const progressErrors = document.getElementById('local-progress-errors');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 処理中...';
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressCount.textContent = '0 / 0';
    currentFileInfo.innerHTML = '<span class="spinner-small"></span><span id="local-current-file-name">準備中...</span>';
    progressErrors.style.display = 'none';

    localProgressInterval = setInterval(pollLocalProgress, 500);
    const formData = new FormData();
    formData.append('llm_engine', selectedEngine);

    try {
        const data = await api.post('/api/local-files/process-all', formData);
        if (data.success) {
            showToast(`${data.total}件のファイルを処理開始しました`);
        } else {
            showToast(data.message || '処理に失敗しました', 'error');
        }
    } catch (error) {
        showToast('処理に失敗しました', 'error');
        if (localProgressInterval) {
            clearInterval(localProgressInterval);
            localProgressInterval = null;
        }
    } finally {
        btn.innerHTML = '⚡ 全て処理';
        // ボタンは完了後に再有効化
        setTimeout(() => {
            btn.disabled = localFiles.length === 0;
        }, 1000);
    }
}

// ============================================
// ページナビゲーション
// ============================================
function setupPageNavigation() {
    const navLinks = document.querySelectorAll('.nav-link[data-page]');
    console.log('Setting up page navigation, found links:', navLinks.length);
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            console.log('Switching to page:', page);
            switchPage(page);
        });
    });
}

function switchPage(page) {
    currentPage = page;

    // ナビリンクの切り替え
    document.querySelectorAll('.nav-link[data-page]').forEach(link => {
        link.classList.toggle('active', link.dataset.page === page);
    });

    // ページコンテンツの切り替え
    document.querySelectorAll('.page-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${page}-page`).classList.add('active');

    // ページごとのデータ読み込み
    if (page === 'signboards') {
        loadSignboards();
    }
}

// ============================================
// 工事看板管理
// ============================================
function setupSignboardModal() {
    const modal = document.getElementById('signboard-modal');
    if (!modal) return;

    document.getElementById('add-signboard-btn').addEventListener('click', () => openSignboardModal());
    document.getElementById('close-signboard-modal').addEventListener('click', () => closeSignboardModal());
    document.getElementById('cancel-signboard-btn').addEventListener('click', () => closeSignboardModal());
    document.getElementById('save-signboard-btn').addEventListener('click', saveSignboard);
    document.getElementById('refresh-signboards-btn').addEventListener('click', loadSignboards);
    document.getElementById('clear-all-signboards-btn').addEventListener('click', clearAllSignboards);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeSignboardModal(); });

    // 履歴モーダルのセットアップ
    setupHistoryModal();
}

// 入出庫履歴モーダル
let allHistoryData = [];
let allSignboardsData = [];

function setupHistoryModal() {
    const modal = document.getElementById('history-modal');
    if (!modal) return;

    document.getElementById('view-history-btn').addEventListener('click', openHistoryModal);
    document.getElementById('close-history-modal').addEventListener('click', closeHistoryModal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeHistoryModal(); });

    // フィルター変更時
    document.getElementById('history-filter-signboard').addEventListener('change', filterHistory);
}

async function openHistoryModal() {
    document.getElementById('history-modal').classList.add('visible');
    await loadHistory();
}

function closeHistoryModal() {
    document.getElementById('history-modal').classList.remove('visible');
}

async function loadHistory() {
    const listEl = document.getElementById('history-list');
    listEl.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        // 履歴と看板一覧を並行取得
        const [historyRes, signboardsRes] = await Promise.all([
            api.get('/api/signboards/history/all'),
            api.get('/api/signboards')
        ]);

        allHistoryData = historyRes.history || [];
        allSignboardsData = signboardsRes.signboards || [];

        // フィルターのオプションを更新
        updateFilterOptions();

        // 履歴を表示
        renderHistory(allHistoryData);
    } catch (error) {
        listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>履歴の読み込みに失敗しました</p></div>';
    }
}

function updateFilterOptions() {
    const select = document.getElementById('history-filter-signboard');
    select.innerHTML = '<option value="">すべて表示</option>';

    allSignboardsData.forEach(s => {
        const option = document.createElement('option');
        option.value = s.id;
        option.textContent = s.comment || `ID: ${s.id}`;
        select.appendChild(option);
    });
}

function filterHistory() {
    const selectedId = document.getElementById('history-filter-signboard').value;

    if (!selectedId) {
        renderHistory(allHistoryData);
    } else {
        const filtered = allHistoryData.filter(h => h.signboard_id == selectedId);
        renderHistory(filtered);
    }
}

function renderHistory(historyList) {
    const listEl = document.getElementById('history-list');

    if (historyList.length === 0) {
        listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><p>履歴がありません</p></div>';
        return;
    }

    // 日付でソート（新しい順）
    const sorted = [...historyList].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    listEl.innerHTML = `
        <table class="history-table">
            <thead>
                <tr>
                    <th>日時</th>
                    <th>看板</th>
                    <th>種別</th>
                    <th>数量</th>
                    <th>理由</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map(h => {
                    const date = new Date(h.created_at).toLocaleString('ja-JP');
                    const typeClass = h.change_type === 'add' ? 'history-add' : 'history-subtract';
                    const typeLabel = h.change_type === 'add' ? '入庫' : '出庫';
                    const signLabel = h.signboard_name || `ID: ${h.signboard_id}`;
                    const qtyChange = h.change_type === 'add' ? `+${h.change_amount}` : `-${h.change_amount}`;
                    return `
                        <tr class="${typeClass}">
                            <td>${date}</td>
                            <td>${signLabel}</td>
                            <td><span class="history-badge ${typeClass}">${typeLabel}</span></td>
                            <td>${qtyChange} (${h.quantity_before}→${h.quantity_after})</td>
                            <td>${h.reason || '-'}</td>
                        </tr>`;
                }).join('')}
            </tbody>
        </table>`;
}

function openSignboardModal(signboard = null) {
    editingSignboardId = signboard ? signboard.id : null;
    const title = document.getElementById('signboard-modal-title');
    title.textContent = signboard ? '🪧 工事看板編集' : '🪧 工事看板登録';

    document.getElementById('signboard-comment').value = signboard?.comment || '';
    document.getElementById('signboard-description').value = signboard?.description || '';
    document.getElementById('signboard-size').value = signboard?.size || '';
    document.getElementById('signboard-quantity').value = signboard?.quantity ?? 1;
    document.getElementById('signboard-location').value = signboard?.location || '';
    document.getElementById('signboard-status').value = signboard?.status || '在庫あり';
    document.getElementById('signboard-notes').value = signboard?.notes || '';

    // テンプレート関連のリセット
    const templateIdEl = document.getElementById('signboard-template-id');
    if (templateIdEl) templateIdEl.value = '';
    const previewEl = document.getElementById('signboard-image-preview');
    if (previewEl) previewEl.innerHTML = '';
    const uploadInput = document.getElementById('signboard-image-upload');
    if (uploadInput) uploadInput.value = '';

    // テンプレート画像を読み込み
    loadSignboardTemplates();

    document.getElementById('signboard-modal').classList.add('visible');
}

// テンプレート画像読み込み
async function loadSignboardTemplates() {
    const loadingEl = document.getElementById('signboard-templates-loading');
    const gridEl = document.getElementById('signboard-templates-grid');
    const errorEl = document.getElementById('signboard-templates-error');

    if (!loadingEl || !gridEl || !errorEl) return;

    loadingEl.style.display = 'block';
    gridEl.style.display = 'none';
    errorEl.style.display = 'none';

    try {
        const response = await fetch('/api/google-drive/signboard-templates');
        if (!response.ok) throw new Error('テンプレート読み込み失敗');

        const data = await response.json();
        const files = data.files || [];

        if (files.length === 0) {
            loadingEl.textContent = 'テンプレート画像がありません';
            return;
        }

        gridEl.innerHTML = files.map(f => `
            <div class="template-item" data-id="${f.id}" data-name="${escapeHtml(f.name)}" onclick="selectSignboardTemplate('${f.id}', '${escapeHtml(f.name)}')">
                <img src="${f.thumbnail_url}" alt="${escapeHtml(f.name)}" loading="lazy">
                <div class="template-name">${escapeHtml(f.name.replace(/\.[^.]+$/, ''))}</div>
            </div>
        `).join('');

        loadingEl.style.display = 'none';
        gridEl.style.display = 'grid';
    } catch (error) {
        loadingEl.style.display = 'none';
        errorEl.textContent = '⚠️ テンプレート読み込み失敗（Google Drive未接続の可能性）';
        errorEl.style.display = 'block';
    }
}

// テンプレート選択
window.selectSignboardTemplate = function(id, name) {
    // 選択状態を更新
    document.querySelectorAll('.template-item').forEach(el => el.classList.remove('selected'));
    const selected = document.querySelector(`.template-item[data-id="${id}"]`);
    if (selected) selected.classList.add('selected');

    // 隠しフィールドに設定
    document.getElementById('signboard-template-id').value = id;

    // コメント欄にファイル名を自動入力（拡張子除去）
    const commentInput = document.getElementById('signboard-comment');
    if (!commentInput.value) {
        commentInput.value = name.replace(/\.[^.]+$/, '');
    }

    // アップロードをクリア
    const uploadInput = document.getElementById('signboard-image-upload');
    if (uploadInput) uploadInput.value = '';
    const previewEl = document.getElementById('signboard-image-preview');
    if (previewEl) previewEl.innerHTML = '';
};

function closeSignboardModal() {
    document.getElementById('signboard-modal').classList.remove('visible');
    editingSignboardId = null;
}

async function saveSignboard() {
    const comment = document.getElementById('signboard-comment').value.trim();
    if (!comment) {
        showToast('看板記載内容は必須です', 'error');
        return;
    }

    const btn = document.getElementById('save-signboard-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> 保存中...';

    // テンプレートIDまたはアップロード画像を取得
    const templateIdEl = document.getElementById('signboard-template-id');
    const templateId = templateIdEl ? templateIdEl.value : '';

    let imagePath = null;
    if (templateId) {
        // Google Driveテンプレートを選択した場合
        imagePath = `/api/google-drive/image/${templateId}`;
    }

    const data = {
        comment: comment,
        description: document.getElementById('signboard-description').value.trim() || null,
        size: document.getElementById('signboard-size').value.trim() || null,
        quantity: parseInt(document.getElementById('signboard-quantity').value) || 1,
        location: document.getElementById('signboard-location').value.trim() || null,
        status: document.getElementById('signboard-status').value,
        notes: document.getElementById('signboard-notes').value.trim() || null,
        image_path: imagePath
    };

    try {
        const url = editingSignboardId
            ? `/api/signboards/${editingSignboardId}`
            : '/api/signboards';
        const method = editingSignboardId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error('保存に失敗しました');

        showToast(editingSignboardId ? '工事看板を更新しました' : '工事看板を登録しました');
        closeSignboardModal();
        loadSignboards();
    } catch (error) {
        showToast('保存に失敗しました', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '保存';
    }
}

async function loadSignboards() {
    const container = document.getElementById('signboards-list');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const data = await api.get('/api/signboards');
        const signboards = data.signboards;

        document.getElementById('signboards-count').textContent = signboards.length;
        updateSignboardsSummary(signboards);

        if (signboards.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🪧</div><p>工事看板が登録されていません</p></div>`;
            return;
        }

        // グリッド表示（3列）
        container.innerHTML = `
            <div class="signboards-grid">
                ${signboards.map(renderSignboardCard).join('')}
            </div>`;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>データの読み込みに失敗しました</p></div>`;
    }
}

function renderSignboardCard(signboard) {
    const imagePath = signboard.image_path || '/images/signboards/枠.jpg';
    const quantity = signboard.quantity || 0;

    return `
        <div class="signboard-card">
            <div class="signboard-image">
                <img src="${imagePath}" alt="${signboard.comment}" onerror="this.src='/images/signboards/枠.jpg'">
            </div>
            <div class="signboard-info">
                <div class="signboard-name">${signboard.comment || '-'}</div>
                <div class="signboard-current-qty">現在: <span id="qty-${signboard.id}">${quantity}</span></div>
            </div>
            <div class="signboard-qty-control">
                <div class="qty-buttons-vertical">
                    <button class="qty-btn-v plus" onclick="setSignboardMode(${signboard.id}, 'plus')">＋</button>
                    <button class="qty-btn-v minus" onclick="setSignboardMode(${signboard.id}, 'minus')">−</button>
                </div>
                <div class="qty-input-area">
                    <input type="number" class="qty-input-sm" id="qty-input-${signboard.id}" min="1" value="1" placeholder="数量">
                    <input type="text" class="qty-reason-sm" id="reason-input-${signboard.id}" placeholder="理由（必須）" required>
                    <input type="hidden" id="mode-${signboard.id}" value="plus">
                    <button class="qty-register-btn" onclick="registerSignboardQty(${signboard.id})">登録</button>
                </div>
            </div>
        </div>`;
}

function getStatusClass(status) {
    switch (status) {
        case '在庫あり': return 'instock';
        case '使用中': return 'inuse';
        case '修理中': return 'repair';
        case '廃棄予定': return 'dispose';
        default: return '';
    }
}

function updateSignboardsSummary(signboards) {
    const instock = signboards.filter(s => s.status === '在庫あり').reduce((sum, s) => sum + s.quantity, 0);
    const inuse = signboards.filter(s => s.status === '使用中').reduce((sum, s) => sum + s.quantity, 0);
    const repair = signboards.filter(s => s.status === '修理中').reduce((sum, s) => sum + s.quantity, 0);

    document.getElementById('summary-instock').textContent = instock;
    document.getElementById('summary-inuse').textContent = inuse;
    document.getElementById('summary-repair').textContent = repair;
}

window.editSignboard = async function(id) {
    try {
        const signboard = await api.get(`/api/signboards/${id}`);
        openSignboardModal(signboard);
    } catch (error) {
        showToast('看板情報の読み込みに失敗しました', 'error');
    }
};

window.deleteSignboard = async function(id) {
    if (!confirm('この工事看板を削除しますか?')) return;
    try {
        await api.delete(`/api/signboards/${id}`);
        showToast('工事看板を削除しました');
        loadSignboards();
    } catch (error) {
        showToast('削除に失敗しました', 'error');
    }
};

window.incrementSignboard = async function(id) {
    try {
        const response = await fetch(`/api/signboards/${id}/increment`, { method: 'POST' });
        if (!response.ok) throw new Error('更新失敗');
        const data = await response.json();
        // 数量表示を更新
        const qtyEl = document.getElementById(`qty-${id}`);
        if (qtyEl) qtyEl.textContent = data.signboard.quantity;
        // マイナスボタンの状態を更新
        const card = qtyEl.closest('.signboard-card');
        if (card) {
            const minusBtn = card.querySelector('.qty-btn.minus');
            if (minusBtn) minusBtn.disabled = false;
        }
        updateSignboardsSummaryFromDOM();
    } catch (error) {
        showToast('更新に失敗しました', 'error');
    }
};

window.decrementSignboard = async function(id) {
    try {
        const response = await fetch(`/api/signboards/${id}/decrement`, { method: 'POST' });
        if (!response.ok) throw new Error('更新失敗');
        const data = await response.json();
        // 数量表示を更新
        const qtyEl = document.getElementById(`qty-${id}`);
        if (qtyEl) qtyEl.textContent = data.signboard.quantity;
        // マイナスボタンの状態を更新
        const card = qtyEl.closest('.signboard-card');
        if (card) {
            const minusBtn = card.querySelector('.qty-btn.minus');
            if (minusBtn) minusBtn.disabled = data.signboard.quantity === 0;
        }
        updateSignboardsSummaryFromDOM();
    } catch (error) {
        showToast('更新に失敗しました', 'error');
    }
};

// 数量を追加（理由必須）
window.addSignboardQuantity = async function(id) {
    const inputEl = document.getElementById(`qty-add-${id}`);
    const reasonEl = document.getElementById(`reason-add-${id}`);
    const qtyEl = document.getElementById(`qty-${id}`);
    if (!inputEl || !reasonEl || !qtyEl) return;

    const addValue = parseInt(inputEl.value) || 0;
    const reason = reasonEl.value.trim();

    if (addValue <= 0) {
        showToast('追加する数量を入力してください', 'error');
        return;
    }
    if (!reason) {
        showToast('理由を入力してください', 'error');
        reasonEl.focus();
        return;
    }

    try {
        const response = await fetch(`/api/signboards/${id}/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: addValue, reason: reason })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '更新失敗');
        }

        const data = await response.json();
        qtyEl.textContent = data.signboard.quantity;
        inputEl.value = '';
        reasonEl.value = '';
        showToast(`${addValue}枚追加しました（計${data.signboard.quantity}枚）`);
        updateSignboardsSummaryFromDOM();
    } catch (error) {
        showToast(error.message || '更新に失敗しました', 'error');
    }
};

// 数量を減少（理由必須）
window.subtractSignboardQuantity = async function(id) {
    const inputEl = document.getElementById(`qty-sub-${id}`);
    const reasonEl = document.getElementById(`reason-sub-${id}`);
    const qtyEl = document.getElementById(`qty-${id}`);
    if (!inputEl || !reasonEl || !qtyEl) return;

    const subValue = parseInt(inputEl.value) || 0;
    const reason = reasonEl.value.trim();

    if (subValue <= 0) {
        showToast('減少する数量を入力してください', 'error');
        return;
    }
    if (!reason) {
        showToast('理由を入力してください', 'error');
        reasonEl.focus();
        return;
    }

    try {
        const response = await fetch(`/api/signboards/${id}/subtract`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: subValue, reason: reason })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '更新失敗');
        }

        const data = await response.json();
        qtyEl.textContent = data.signboard.quantity;
        inputEl.value = '';
        reasonEl.value = '';
        showToast(`${subValue}枚減少しました（計${data.signboard.quantity}枚）`);
        updateSignboardsSummaryFromDOM();
    } catch (error) {
        showToast(error.message || '更新に失敗しました', 'error');
    }
};

// +/-モード切替
window.setSignboardMode = function(id, mode) {
    const modeInput = document.getElementById(`mode-${id}`);
    if (modeInput) modeInput.value = mode;

    // ボタンのアクティブ状態を更新
    const card = modeInput.closest('.signboard-card');
    if (card) {
        card.querySelectorAll('.qty-btn-v').forEach(btn => btn.classList.remove('active'));
        card.querySelector(`.qty-btn-v.${mode}`).classList.add('active');

        // 入力エリアの色を変更
        const inputArea = card.querySelector('.qty-input-area');
        if (inputArea) {
            inputArea.classList.remove('mode-plus', 'mode-minus');
            inputArea.classList.add(`mode-${mode}`);
        }
    }
};

// 数量登録
window.registerSignboardQty = async function(id) {
    const modeInput = document.getElementById(`mode-${id}`);
    const qtyInput = document.getElementById(`qty-input-${id}`);
    const reasonInput = document.getElementById(`reason-input-${id}`);
    const qtyDisplay = document.getElementById(`qty-${id}`);

    const mode = modeInput?.value || 'plus';
    const amount = parseInt(qtyInput?.value) || 0;
    const reason = reasonInput?.value?.trim() || '';

    if (amount <= 0) {
        showToast('数量を入力してください', 'error');
        qtyInput?.focus();
        return;
    }

    if (!reason) {
        showToast('理由を入力してください', 'error');
        reasonInput?.focus();
        return;
    }

    const endpoint = mode === 'plus' ? 'add' : 'subtract';

    try {
        const response = await fetch(`/api/signboards/${id}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: amount, reason: reason })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '更新失敗');
        }

        const data = await response.json();
        if (qtyDisplay) qtyDisplay.textContent = data.signboard.quantity;
        qtyInput.value = '1';
        reasonInput.value = '';

        const action = mode === 'plus' ? '追加' : '減少';
        showToast(`${amount}枚${action}しました（計${data.signboard.quantity}枚）`);
        updateSignboardsSummaryFromDOM();
    } catch (error) {
        showToast(error.message || '更新に失敗しました', 'error');
    }
};

function updateSignboardsSummaryFromDOM() {
    // DOMから数量を集計してサマリーを更新
    let total = 0;
    document.querySelectorAll('.qty-value').forEach(el => {
        total += parseInt(el.textContent) || 0;
    });
    document.getElementById('summary-instock').textContent = total;
}

async function clearAllSignboards() {
    if (!confirm('全ての工事看板を削除しますか?')) return;
    try {
        await api.delete('/api/signboards');
        showToast('全ての工事看板を削除しました');
        loadSignboards();
    } catch (error) {
        showToast('削除に失敗しました', 'error');
    }
}
