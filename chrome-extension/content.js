/**
 * content.js — runs on 1688/타오바오/T몰 상품 상세 페이지에서 floating
 * 버튼을 주입하고, 클릭 시 DOM을 파싱해 background worker로 전달한다.
 *
 * 모든 셀렉터는 사이트 업데이트로 깨질 수 있으므로 try/catch로 감싸 빈
 * 결과를 반환하게 한다 — 일부 필드가 빠져도 보낼 수 있는 만큼은 보낸다.
 * 백엔드 ``IngestRequest`` 스키마는 ``main_images`` 만 필수라서, 최소한
 * 이미지 1장과 title은 확보해야 ingest 가 성공한다.
 */
(function () {
  'use strict';

  if (window.__itemSelectorInjected) return;
  window.__itemSelectorInjected = true;

  // -------------------------------------------------------------------
  // Platform detection
  // -------------------------------------------------------------------
  /** @returns {'1688'|'taobao'|null} */
  function detectPlatform() {
    const host = location.hostname;
    if (host.includes('1688.com')) return '1688';
    // tmall도 백엔드 schema 상 'taobao' 로 보냄 (Literal['1688','taobao']).
    if (host.includes('taobao.com') || host.includes('tmall.com')) return 'taobao';
    return null;
  }

  const PLATFORM = detectPlatform();
  if (!PLATFORM) return;

  // -------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------
  function safe(fn, fallback) {
    try {
      const v = fn();
      return v === undefined || v === null ? fallback : v;
    } catch (err) {
      console.warn('[itemSelector] selector failed:', err);
      return fallback;
    }
  }

  /** Schemeless (//img...) URL을 https:로 변환하고, 1688 60x60 썸네일을 원본으로 업그레이드. */
  function normalizeImageUrl(raw) {
    if (!raw || typeof raw !== 'string') return null;
    let url = raw.trim();
    if (!url) return null;
    if (url.startsWith('//')) url = 'https:' + url;
    if (url.startsWith('http://')) url = 'https://' + url.slice(7);
    if (!url.startsWith('https://')) return null;
    // 1688 thumbnail upgrade: foo_60x60.jpg → foo.jpg
    url = url.replace(/_\d+x\d+(\.(jpg|jpeg|png|webp))/i, '$1');
    // 무효한 1x1 placeholder 방어
    if (url.includes('s.gif') || url.endsWith('blank.gif')) return null;
    return url;
  }

  function dedupe(arr) {
    return Array.from(new Set(arr.filter(Boolean)));
  }

  function pickAttr(el, attrs) {
    if (!el) return null;
    for (const a of attrs) {
      const v = el.getAttribute(a);
      if (v) return v;
    }
    return null;
  }

  function parsePrice(text) {
    if (!text) return null;
    const m = String(text).replace(/[^\d.]/g, '');
    if (!m) return null;
    const n = parseFloat(m);
    return Number.isFinite(n) ? n : null;
  }

  function textOf(sel, root) {
    const el = (root || document).querySelector(sel);
    return el ? (el.textContent || '').trim() : '';
  }

  function imgSrc(el) {
    if (!el) return null;
    return normalizeImageUrl(
      pickAttr(el, ['data-src', 'data-lazy-src', 'data-original', 'src'])
    );
  }

  function collectImgs(selector, root) {
    const els = (root || document).querySelectorAll(selector);
    const urls = [];
    els.forEach((el) => {
      const u = imgSrc(el);
      if (u) urls.push(u);
    });
    return dedupe(urls);
  }

  // -------------------------------------------------------------------
  // 1688 parser
  // -------------------------------------------------------------------
  function parse1688() {
    const title = safe(
      () => textOf('h1.title-text') ||
            textOf('.title-content h1') ||
            textOf('.d-title h1') ||
            textOf('h1.d-title') ||
            textOf('h1') ||
            document.title.split('-')[0].trim(),
      ''
    );

    const price = safe(() => {
      const candidates = [
        '.price-original',
        '.price-now',
        '.price-num',
        '.mod-detail-price .value',
        '.price',
        '[data-price]',
      ];
      for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const dp = el.getAttribute('data-price');
        const v = parsePrice(dp || el.textContent);
        if (v !== null) return v;
      }
      return null;
    }, null);

    const mainImages = safe(() => {
      const found = [];
      const main = document.querySelector('.main-image img, .tab-trigger.active img');
      const m = imgSrc(main);
      if (m) found.push(m);
      collectImgs('.tab-trigger img, .img-list img, .od-gallery-thumbs img').forEach((u) => found.push(u));
      return dedupe(found);
    }, []);

    const detailImages = safe(
      () => collectImgs('#desc img, .content-detail img, .desc-content img, .desc-lazyload-container img, [class*="desc"] img'),
      []
    );

    const specs = safe(() => {
      const out = {};
      // pattern 1: <dl><dt>label</dt><dd>value</dd></dl>
      document.querySelectorAll('.attributes-list dt, .od-pc-attribute dt').forEach((dt) => {
        const dd = dt.nextElementSibling;
        if (dd) {
          const k = (dt.textContent || '').trim().replace(/[:：]\s*$/, '');
          const v = (dd.textContent || '').trim();
          if (k && v) out[k] = v;
        }
      });
      // pattern 2: <table><tr><td label></td><td value></td></tr></table>
      document.querySelectorAll('.obj-content tr, .attributes tr').forEach((tr) => {
        const cells = tr.querySelectorAll('td, th');
        for (let i = 0; i < cells.length - 1; i += 2) {
          const k = (cells[i].textContent || '').trim().replace(/[:：]\s*$/, '');
          const v = (cells[i + 1].textContent || '').trim();
          if (k && v) out[k] = v;
        }
      });
      // pattern 3: <ul><li><span>label</span><span>value</span></li></ul>
      document.querySelectorAll('.attribute-list li, .od-pc-attribute li').forEach((li) => {
        const spans = li.querySelectorAll('span');
        if (spans.length >= 2) {
          const k = (spans[0].textContent || '').trim().replace(/[:：]\s*$/, '');
          const v = (spans[1].textContent || '').trim();
          if (k && v) out[k] = v;
        }
      });
      return out;
    }, {});

    const categoryPath = safe(() => {
      const crumbs = document.querySelectorAll(
        '.breadcrumb a, .crumbs a, .od-pc-breadcrumb a, [class*="breadcrumb"] a'
      );
      const arr = [];
      crumbs.forEach((a) => {
        const t = (a.textContent || '').trim();
        if (t && t !== '首页' && t !== 'Home') arr.push(t);
      });
      return arr;
    }, []);

    const optionImages = safe(() => {
      const out = [];
      document.querySelectorAll('.sku-item, .obj-sku-item, [class*="sku"] [class*="item"]').forEach((el) => {
        const img = el.querySelector('img');
        const url = imgSrc(img);
        if (!url) return;
        const name =
          (el.getAttribute('title') ||
            el.getAttribute('data-name') ||
            (el.textContent || '').trim() ||
            'option').slice(0, 64);
        out.push({ name, url });
      });
      return out;
    }, []);

    return { title, price, mainImages, detailImages, specs, categoryPath, optionImages };
  }

  // -------------------------------------------------------------------
  // Taobao / Tmall parser
  // -------------------------------------------------------------------
  function parseTaobao() {
    const title = safe(() => {
      const candidates = [
        '.tb-detail-hd h1',
        '.tb-main-title',
        '[data-spm="item-detail"] h1',
        '.tb-detail-hd h3',
        'h1',
      ];
      for (const sel of candidates) {
        const t = textOf(sel);
        if (t) return t;
      }
      const meta = document.querySelector('meta[name="keywords"]');
      if (meta) {
        const c = meta.getAttribute('content') || '';
        const first = c.split(/[,，]/)[0].trim();
        if (first) return first;
      }
      return document.title.split('-')[0].trim();
    }, '');

    const price = safe(() => {
      const candidates = [
        '.tm-price',
        '.tb-rmb-num',
        '.J_PromoPriceNum',
        '.tm-price-cur .tm-price',
        '#J_PromoPrice .tm-price',
        '[class*="Price--priceText"]',
        '.price',
      ];
      for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const v = parsePrice(el.textContent);
        if (v !== null) return v;
      }
      return null;
    }, null);

    const mainImages = safe(() => {
      const found = [];
      const main = document.querySelector('#J_ImgBooth, .tb-pic img, .tb-main-pic img');
      const m = imgSrc(main);
      if (m) found.push(m);
      collectImgs('#J_UlThumb img, .tb-thumb img, .tb-s40 img, [class*="Thumbnail"] img').forEach((u) =>
        found.push(u)
      );
      return dedupe(found);
    }, []);

    const detailImages = safe(
      () => collectImgs('#description img, .J_DetailMeta img, #J_DivItemDesc img, [class*="desc"] img'),
      []
    );

    const specs = safe(() => {
      const out = {};
      document.querySelectorAll('.attributes-list li, .Attributes--list li, ul.attributes li').forEach((li) => {
        const text = (li.textContent || '').trim();
        // "라벨: 값" or "라벨：값" — split on first colon
        const m = text.match(/^([^:：]+)[：:]\s*(.+)$/);
        if (m) {
          const k = m[1].trim();
          const v = m[2].trim();
          if (k && v) out[k] = v;
        }
      });
      // Tmall 신형 attribute table
      document.querySelectorAll('.attributes-list tr, .Attributes--table tr').forEach((tr) => {
        const cells = tr.querySelectorAll('td, th');
        for (let i = 0; i < cells.length - 1; i += 2) {
          const k = (cells[i].textContent || '').trim().replace(/[:：]\s*$/, '');
          const v = (cells[i + 1].textContent || '').trim();
          if (k && v) out[k] = v;
        }
      });
      return out;
    }, {});

    const categoryPath = safe(() => {
      const crumbs = document.querySelectorAll(
        '.breadcrumb a, .tb-breadcrumb a, [class*="Breadcrumb"] a'
      );
      const arr = [];
      crumbs.forEach((a) => {
        const t = (a.textContent || '').trim();
        if (t && t !== '首页' && t !== 'Home') arr.push(t);
      });
      return arr;
    }, []);

    const optionImages = safe(() => {
      const out = [];
      document
        .querySelectorAll('.J_TSaleProp li, .tb-sku li, [class*="SkuContent"] li, [class*="skuItem"]')
        .forEach((el) => {
          const img = el.querySelector('img') || el.querySelector('a');
          let url = imgSrc(el.querySelector('img'));
          if (!url && img && img.style && img.style.backgroundImage) {
            const bg = img.style.backgroundImage.match(/url\(["']?([^"')]+)["']?\)/);
            if (bg) url = normalizeImageUrl(bg[1]);
          }
          if (!url) return;
          const name =
            (el.getAttribute('title') ||
              el.getAttribute('data-value') ||
              (el.textContent || '').trim() ||
              'option').slice(0, 64);
          out.push({ name, url });
        });
      return out;
    }, []);

    return { title, price, mainImages, detailImages, specs, categoryPath, optionImages };
  }

  // -------------------------------------------------------------------
  // Build payload
  // -------------------------------------------------------------------
  function buildPayload() {
    const parsed = PLATFORM === '1688' ? parse1688() : parseTaobao();

    return {
      source_url: location.href.split('#')[0],
      source_platform: PLATFORM,
      title_zh: parsed.title || '(제목 추출 실패)',
      price_cny: parsed.price,
      category_path: parsed.categoryPath,
      specs: parsed.specs,
      main_images: parsed.mainImages,
      detail_images: parsed.detailImages,
      option_images: parsed.optionImages,
    };
  }

  // -------------------------------------------------------------------
  // UI: floating button + status
  // -------------------------------------------------------------------
  function injectButton() {
    const wrapper = document.createElement('div');
    wrapper.id = '__itemSelector_wrapper';
    wrapper.style.cssText = [
      'position:fixed',
      'top:80px',
      'right:16px',
      'z-index:2147483647',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
      'display:flex',
      'flex-direction:column',
      'align-items:flex-end',
      'gap:8px',
      'pointer-events:none',
    ].join(';');

    const btn = document.createElement('button');
    btn.id = '__itemSelector_btn';
    btn.type = 'button';
    btn.textContent = '🎨 상세페이지 생성';
    btn.style.cssText = [
      'pointer-events:auto',
      'background:#1e293b',
      'color:#f8fafc',
      'border:none',
      'border-radius:8px',
      'padding:12px 18px',
      'font-size:14px',
      'font-weight:600',
      'cursor:pointer',
      'box-shadow:0 4px 12px rgba(0,0,0,0.25)',
      'transition:background 120ms ease,transform 120ms ease',
    ].join(';');
    btn.addEventListener('mouseenter', () => {
      btn.style.background = '#334155';
      btn.style.transform = 'translateY(-1px)';
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.background = '#1e293b';
      btn.style.transform = 'translateY(0)';
    });

    const status = document.createElement('div');
    status.id = '__itemSelector_status';
    status.style.cssText = [
      'pointer-events:auto',
      'min-height:0',
      'max-width:320px',
      'background:rgba(15,23,42,0.92)',
      'color:#f8fafc',
      'border-radius:6px',
      'padding:0',
      'font-size:12px',
      'line-height:1.4',
      'box-shadow:0 4px 12px rgba(0,0,0,0.2)',
      'word-break:break-word',
      'opacity:0',
      'transition:opacity 150ms ease',
    ].join(';');

    function setStatus(msg, kind) {
      status.textContent = msg;
      status.style.padding = msg ? '8px 12px' : '0';
      status.style.opacity = msg ? '1' : '0';
      const colors = {
        info: '#1e293b',
        success: '#166534',
        error: '#991b1b',
      };
      status.style.background = colors[kind] || colors.info;
    }

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const original = btn.textContent;
      btn.textContent = '⏳ 전송 중…';
      setStatus('페이지를 파싱하는 중…', 'info');

      let payload;
      try {
        payload = buildPayload();
      } catch (err) {
        setStatus('❌ 파싱 실패: ' + (err && err.message ? err.message : String(err)), 'error');
        btn.disabled = false;
        btn.textContent = original;
        return;
      }

      if (!payload.main_images || payload.main_images.length === 0) {
        setStatus('❌ 메인 이미지를 찾지 못했습니다. 페이지를 새로고침 후 다시 시도하세요.', 'error');
        btn.disabled = false;
        btn.textContent = original;
        return;
      }

      setStatus('백엔드로 전송 중…', 'info');

      let response;
      try {
        response = await chrome.runtime.sendMessage({ type: 'INGEST', payload });
      } catch (err) {
        setStatus('❌ 확장 통신 실패: ' + (err && err.message ? err.message : String(err)), 'error');
        btn.disabled = false;
        btn.textContent = original;
        return;
      }

      if (!response) {
        setStatus('❌ 응답 없음 (background worker 확인)', 'error');
      } else if (response.ok) {
        const data = response.data || {};
        const id = data.id ?? '?';
        setStatus(`✅ 등록됨 (id #${id}) — 백엔드에서 생성 진행 중`, 'success');
      } else {
        const reason = response.error || `HTTP ${response.status || '???'}`;
        setStatus(`❌ 실패: ${reason}`, 'error');
      }

      btn.disabled = false;
      btn.textContent = original;
    });

    wrapper.appendChild(btn);
    wrapper.appendChild(status);
    document.body.appendChild(wrapper);
  }

  // body 가 아직 없으면 대기
  if (document.body) {
    injectButton();
  } else {
    document.addEventListener('DOMContentLoaded', injectButton, { once: true });
  }
})();
