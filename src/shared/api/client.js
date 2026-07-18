export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs || 10000;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const requestOptions = { ...options, signal: options.signal || controller.signal };
  delete requestOptions.timeoutMs;

  try {
    const response = await fetch('/api' + path, requestOptions);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const error = new Error(payload?.detail || payload || `请求失败 (${response.status})`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  } catch (error) {
    if (error?.name === 'AbortError') {
      const timeoutError = new Error('请求超时，该模块暂时不可用');
      timeoutError.code = 'request_timeout';
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
