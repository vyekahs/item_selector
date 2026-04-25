/**
 * popup.js — 백엔드 URL + basic auth 자격증명을 chrome.storage.sync 에 저장하고
 * 연결 테스트 (GET /detail-pages?limit=1) 를 수행한다.
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const STORAGE_KEYS = ['backendUrl', 'username', 'password'];

  function setStatus(msg, kind) {
    const el = $('status');
    el.className = 'status' + (kind ? ' ' + kind : '');
    el.textContent = msg || '';
    if (!msg) el.style.display = 'none';
  }

  async function load() {
    const cfg = await chrome.storage.sync.get(STORAGE_KEYS);
    $('backendUrl').value = cfg.backendUrl || '';
    $('username').value = cfg.username || '';
    $('password').value = cfg.password || '';
  }

  function readForm() {
    return {
      backendUrl: $('backendUrl').value.trim().replace(/\/+$/, ''),
      username: $('username').value.trim(),
      password: $('password').value,
    };
  }

  async function save() {
    const cfg = readForm();
    if (!cfg.backendUrl) {
      setStatus('❌ 백엔드 URL을 입력하세요.', 'error');
      return false;
    }
    try {
      // sanity check: must be a valid URL
      new URL(cfg.backendUrl);
    } catch {
      setStatus('❌ 올바른 URL 형식이 아닙니다.', 'error');
      return false;
    }
    await chrome.storage.sync.set(cfg);
    setStatus('✅ 저장되었습니다.', 'success');
    return true;
  }

  async function test() {
    if (!(await save())) return;

    const btn = $('testBtn');
    btn.disabled = true;
    setStatus('🩺 연결 테스트 중…', 'info');

    let res;
    try {
      res = await chrome.runtime.sendMessage({ type: 'PING' });
    } catch (err) {
      setStatus('❌ 확장 통신 실패: ' + (err && err.message ? err.message : String(err)), 'error');
      btn.disabled = false;
      return;
    }

    if (!res) {
      setStatus('❌ 응답 없음 (background worker 확인)', 'error');
    } else if (res.ok) {
      setStatus(`✅ ${res.status || 200} OK — 백엔드 연결 성공`, 'success');
    } else {
      setStatus('❌ ' + (res.error || '알 수 없는 오류'), 'error');
    }
    btn.disabled = false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    load().catch((err) => setStatus('❌ 설정 로드 실패: ' + err, 'error'));
    $('saveBtn').addEventListener('click', () => save().catch((e) => setStatus('❌ ' + e, 'error')));
    $('testBtn').addEventListener('click', () => test().catch((e) => setStatus('❌ ' + e, 'error')));
  });
})();
