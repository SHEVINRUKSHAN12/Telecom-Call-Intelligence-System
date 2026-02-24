const host = window.location.hostname;
const apiHost = host === '0.0.0.0' || host === '' || host === 'localhost' ? '127.0.0.1' : host;
const API_BASE_URL = `${window.location.protocol}//${apiHost}:8000/api`;
const HEALTH_URL = `${window.location.protocol}//${apiHost}:8000/health`;

async function requestJson(url, options) {
    try {
        const response = await fetch(url, options);
        return response;
    } catch (error) {
        throw new Error(`Cannot reach backend at ${API_BASE_URL}. Ensure backend is running on port 8000.`);
    }
}

const buildQuery = (params = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            search.append(key, value);
        }
    });
    const queryString = search.toString();
    return queryString ? `?${queryString}` : '';
};

export async function uploadCall(audioFile) {
    const formData = new FormData();
    formData.append('file', audioFile);

    const response = await requestJson(`${API_BASE_URL}/calls`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Call analysis failed');
    }

    return response.json();
}

export async function fetchCalls(params = {}) {
    const response = await requestJson(`${API_BASE_URL}/calls${buildQuery(params)}`);
    if (!response.ok) {
        throw new Error('Failed to fetch calls');
    }
    return response.json();
}

export async function fetchCallById(callId) {
    const response = await requestJson(`${API_BASE_URL}/calls/${callId}`);
    if (!response.ok) {
        throw new Error('Failed to fetch call');
    }
    return response.json();
}

export async function fetchCallAudioUrl(callId) {
    const response = await requestJson(`${API_BASE_URL}/calls/${callId}/audio-url`);
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to get audio URL');
    }
    return response.json();
}

export async function fetchAnalytics(params = {}) {
    const response = await requestJson(`${API_BASE_URL}/analytics${buildQuery(params)}`);
    if (!response.ok) {
        throw new Error('Failed to fetch analytics');
    }
    return response.json();
}

export async function checkHealth() {
    const response = await requestJson(HEALTH_URL);
    return response.json();
}
