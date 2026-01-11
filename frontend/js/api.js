// API Client
// 相対パスを使用（本番環境でも動作するように）
const API_URL = '';

export const api = {
    async get(endpoint) {
        const response = await fetch(`${API_URL}${endpoint}`);
        return response.json();
    },

    async post(endpoint, data = null) {
        const options = { method: 'POST' };
        if (data) options.body = data;
        const response = await fetch(`${API_URL}${endpoint}`, options);
        return response.json();
    },

    async delete(endpoint) {
        const response = await fetch(`${API_URL}${endpoint}`, { method: 'DELETE' });
        return response.json();
    },

    async getBlob(endpoint) {
        const response = await fetch(`${API_URL}${endpoint}`);
        if (!response.ok) throw new Error((await response.json()).detail);
        return response.blob();
    }
};
