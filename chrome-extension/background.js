/**
 * background.js — service worker.
 *
 * content.js (또는 popup.js) 가 보내는 메시지를 받아 백엔드로 fetch 한다.
 * SW 컨텍스트에서 fetch 하는 이유:
 *   1. host_permissions 가 적용되어 CORS 우회가 가능 (페이지 origin 무관).
 *   2. Authorization 헤더를 안전하게 부착 (페이지 JS와 분리).
 *
 * 메시지 프로토콜:
 *   {type:'INGEST', payload:{...}}     → POST /detail-pages/ingest
 *   {type:'PING'}                       → GET  /detail-pages?limit=1 (popup 연결 테스트)
 *   응답: {ok:boolean, status?:number, data?:any, error?:string}
 */

const STORAGE_KEYS = ['backendUrl', 'username', 'password'];

async function getConfig() {
  const cfg = await chrome.storage.sync.get(STORAGE_KEYS);
  return {
    backendUrl: (cfg.backendUrl || '').trim().replace(/\/+$/, ''),
    username: cfg.username || '',
    password: cfg.password || '',
  };
}

function authHeader(username, password) {
  if (!username && !password) return null;
  // btoa 는 UTF-8 비ASCII 에서 깨질 수 있으므로 안전하게 인코딩.
  const raw = `${username}:${password}`;
  const utf8 = new TextEncoder().encode(raw);
  let bin = '';
  utf8.forEach((b) => (bin += String.fromCharCode(b)));
  return 'Basic ' + btoa(bin);
}

async function callBackend({ method, path, body }) {
  const cfg = await getConfig();
  if (!cfg.backendUrl) {
    return { ok: false, error: '백엔드 URL이 설정되지 않았습니다. 확장 팝업에서 설정하세요.' };
  }

  const url = cfg.backendUrl + path;
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
  const auth = authHeader(cfg.username, cfg.password);
  if (auth) headers['Authorization'] = auth;

  let res;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    return { ok: false, error: 'fetch 실패: ' + (err && err.message ? err.message : String(err)) };
  }

  let data = null;
  let text = '';
  try {
    text = await res.text();
    if (text) data = JSON.parse(text);
  } catch {
    data = text || null;
  }

  if (!res.ok) {
    let detail = '';
    if (data && typeof data === 'object') {
      detail = data.detail || data.message || JSON.stringify(data);
    } else if (typeof data === 'string') {
      detail = data;
    }
    return {
      ok: false,
      status: res.status,
      error: `HTTP ${res.status}${detail ? ' — ' + String(detail).slice(0, 240) : ''}`,
      data,
    };
  }

  return { ok: true, status: res.status, data };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== 'object') {
    sendResponse({ ok: false, error: 'invalid message' });
    return false;
  }

  if (msg.type === 'INGEST') {
    callBackend({ method: 'POST', path: '/detail-pages/ingest', body: msg.payload })
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // async response
  }

  if (msg.type === 'PING') {
    callBackend({ method: 'GET', path: '/detail-pages?limit=1' })
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  sendResponse({ ok: false, error: 'unknown message type: ' + msg.type });
  return false;
});
