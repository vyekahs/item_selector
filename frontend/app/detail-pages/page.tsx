'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import { API_BASE_URL } from '@/lib/api/client';
import { useDetailPages, useDetailPageTemplates } from '@/lib/api/queries';
import { useIngestDetailPage } from '@/lib/api/mutations';
import type { DetailPageStatus } from '@/lib/api/types';

const PAGE_SIZE = 20;

const statusLabel: Record<DetailPageStatus, string> = {
  pending: '대기 중',
  processing: '처리 중',
  done: '완료',
  failed: '실패',
};

const statusBadgeClass: Record<DetailPageStatus, string> = {
  pending: 'bg-slate-100 text-slate-700 border-slate-200',
  processing: 'bg-sky-100 text-sky-700 border-sky-200',
  done: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-100 text-rose-700 border-rose-200',
};

function StatusBadge({ status }: { status: DetailPageStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${statusBadgeClass[status]}`}
    >
      {statusLabel[status]}
    </span>
  );
}

function parseLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function parseSpecs(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of parseLines(text)) {
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (key && value) result[key] = value;
  }
  return result;
}

export default function DetailPagesListPage() {
  const topRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(0);
  const offset = page * PAGE_SIZE;
  const { data, isLoading, isError, error } = useDetailPages({
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = useMemo(() => {
    if (!data) return 0;
    return Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  }, [data]);

  // Manual ingest form state
  const [formOpen, setFormOpen] = useState(false);
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourcePlatform, setSourcePlatform] = useState<'1688' | 'taobao'>('1688');
  const [titleZh, setTitleZh] = useState('');
  const [priceCny, setPriceCny] = useState('');
  const [mainImagesText, setMainImagesText] = useState('');
  const [detailImagesText, setDetailImagesText] = useState('');
  const [specsText, setSpecsText] = useState('');
  const [templateName, setTemplateName] = useState<string>('');
  const [flash, setFlash] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(
    null,
  );

  const ingest = useIngestDetailPage();
  const templatesQuery = useDetailPageTemplates();
  const templates = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data]);

  // Default the picker to the first option once templates load.
  useEffect(() => {
    if (templates.length > 0 && templateName === '') {
      setTemplateName(templates[0].name);
    }
  }, [templates, templateName]);

  const templateLabelByName = useMemo(() => {
    const map: Record<string, string> = {};
    for (const t of templates) map[t.name] = t.label;
    return map;
  }, [templates]);

  const selectedTemplate = templates.find((t) => t.name === templateName);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFlash(null);

    const mainImages = parseLines(mainImagesText);
    const detailImages = parseLines(detailImagesText);
    const specs = parseSpecs(specsText);

    if (!sourceUrl.trim()) {
      setFlash({ kind: 'err', msg: '❌ Source URL을 입력하세요.' });
      return;
    }
    if (!titleZh.trim()) {
      setFlash({ kind: 'err', msg: '❌ 중국어 제목을 입력하세요.' });
      return;
    }
    if (mainImages.length === 0) {
      setFlash({ kind: 'err', msg: '❌ 메인 이미지 URL을 1개 이상 입력하세요.' });
      return;
    }

    const body: Record<string, unknown> = {
      source_url: sourceUrl.trim(),
      source_platform: sourcePlatform,
      title_zh: titleZh.trim(),
      main_images: mainImages,
      detail_images: detailImages,
      specs,
    };
    const priceNum = Number(priceCny);
    if (priceCny.trim() && Number.isFinite(priceNum) && priceNum >= 0) {
      body.price_cny = priceNum;
    }
    if (templateName) {
      body.template_name = templateName;
    }

    try {
      await ingest.mutateAsync(body);
      setFlash({
        kind: 'ok',
        msg: '✅ 생성 시작됨. 1~2분 후 새로고침',
      });
      // Reset form fields
      setSourceUrl('');
      setTitleZh('');
      setPriceCny('');
      setMainImagesText('');
      setDetailImagesText('');
      setSpecsText('');
      setPage(0);
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      setFlash({
        kind: 'err',
        msg: `❌ 생성 실패: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  };

  return (
    <div ref={topRef} className="flex flex-col gap-5">
      <header>
        <h1 className="text-xl font-bold text-slate-900">🎨 상세페이지 생성</h1>
        <p className="mt-1 text-sm text-slate-500">
          1688/타오바오 상품 데이터를 입력하면 한국어 카피라이팅 + 한국식 상세페이지
          이미지를 자동 생성합니다.
        </p>
      </header>

      <section className="card flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            ➕ 수동 입력 (Chrome Extension 없이 추가)
          </h2>
          <button
            type="button"
            className="btn-secondary text-xs"
            onClick={() => setFormOpen((v) => !v)}
            aria-expanded={formOpen}
          >
            {formOpen ? '접기' : '펼치기'}
          </button>
        </div>

        {formOpen && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">Source URL</span>
                <input
                  type="url"
                  className="input"
                  placeholder="https://detail.1688.com/offer/..."
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  required
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-slate-500">플랫폼</span>
                <select
                  className="input"
                  value={sourcePlatform}
                  onChange={(e) =>
                    setSourcePlatform(e.target.value as '1688' | 'taobao')
                  }
                >
                  <option value="1688">1688</option>
                  <option value="taobao">타오바오</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-slate-500">단가 (CNY, 선택)</span>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  className="input"
                  placeholder="예: 28"
                  value={priceCny}
                  onChange={(e) => setPriceCny(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">중국어 제목</span>
                <input
                  type="text"
                  className="input"
                  value={titleZh}
                  onChange={(e) => setTitleZh(e.target.value)}
                  required
                />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">
                  메인 이미지 URL (한 줄에 하나씩)
                </span>
                <textarea
                  className="input min-h-[80px] font-mono text-xs"
                  value={mainImagesText}
                  onChange={(e) => setMainImagesText(e.target.value)}
                  placeholder="https://...jpg&#10;https://...jpg"
                  required
                />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">
                  상세 이미지 URL (선택, 한 줄에 하나씩)
                </span>
                <textarea
                  className="input min-h-[80px] font-mono text-xs"
                  value={detailImagesText}
                  onChange={(e) => setDetailImagesText(e.target.value)}
                  placeholder="https://...jpg"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">
                  스펙 (`키: 값` 한 줄에 하나씩)
                </span>
                <textarea
                  className="input min-h-[80px] font-mono text-xs"
                  value={specsText}
                  onChange={(e) => setSpecsText(e.target.value)}
                  placeholder="무게: 0.5kg&#10;사이즈: M/L"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-xs text-slate-500">템플릿</span>
                <select
                  className="input"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  disabled={templates.length === 0}
                >
                  {templates.length === 0 && (
                    <option value="">불러오는 중…</option>
                  )}
                  {templates.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.label}
                    </option>
                  ))}
                </select>
                {selectedTemplate && (
                  <small className="text-xs text-slate-400">
                    {selectedTemplate.description}
                  </small>
                )}
              </label>
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="btn-primary"
                disabled={ingest.isPending}
              >
                {ingest.isPending ? '제출 중…' : '🚀 생성 요청'}
              </button>
            </div>
          </form>
        )}

        {flash && (
          <p
            role={flash.kind === 'err' ? 'alert' : 'status'}
            className={`rounded-md px-3 py-2 text-sm ${
              flash.kind === 'ok'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-rose-50 text-rose-700'
            }`}
          >
            {flash.msg}
          </p>
        )}
      </section>

      {isLoading ? (
        <p role="status" className="text-sm text-slate-500">
          불러오는 중…
        </p>
      ) : isError ? (
        <p
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        >
          목록을 불러오지 못했습니다: {error.message}
        </p>
      ) : !data || data.items.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          아직 생성된 상세페이지가 없습니다. 위 입력 폼으로 시작하세요.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">ID</th>
                  <th className="py-2">미리보기</th>
                  <th className="py-2">제목 (KO)</th>
                  <th className="py-2">상태</th>
                  <th className="py-2">템플릿</th>
                  <th className="py-2">원본</th>
                  <th className="py-2">생성 시각</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((dp) => {
                  const thumbUrl =
                    dp.image_path && dp.status === 'done'
                      ? `${API_BASE_URL}/generated/${dp.image_path}`
                      : null;
                  return (
                    <tr
                      key={dp.id}
                      className="border-b border-slate-100 align-top"
                    >
                      <td className="py-2 pr-2 text-xs text-slate-500 tabular-nums">
                        #{dp.id}
                      </td>
                      <td className="py-2 pr-2">
                        {thumbUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={thumbUrl}
                            alt={`상세페이지 ${dp.id} 썸네일`}
                            className="h-10 w-10 rounded border border-slate-200 object-cover"
                          />
                        ) : (
                          <div className="flex h-10 w-10 items-center justify-center rounded border border-dashed border-slate-300 text-[10px] text-slate-400">
                            —
                          </div>
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        <div className="font-medium text-slate-900">
                          {dp.title_ko ?? (
                            <span className="text-slate-400">—</span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={dp.status} />
                      </td>
                      <td className="py-2 pr-2 text-xs text-slate-600">
                        {templateLabelByName[dp.template_name] ?? dp.template_name}
                      </td>
                      <td className="py-2 pr-2">
                        <a
                          href={dp.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-brand-600 hover:underline"
                          title={dp.source_url}
                        >
                          {dp.source_platform} ↗
                        </a>
                      </td>
                      <td className="py-2 pr-2 text-xs text-slate-500">
                        {new Date(dp.created_at).toLocaleString('ko-KR')}
                      </td>
                      <td className="py-2">
                        <Link
                          href={`/detail-pages/${dp.id}`}
                          className="text-xs text-brand-600 hover:underline"
                        >
                          보기 →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <nav
            aria-label="페이지네이션"
            className="flex items-center justify-between text-sm text-slate-600"
          >
            <span>
              총 {data.total}건 · 페이지 {page + 1} / {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-secondary"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                이전
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </button>
            </div>
          </nav>
        </>
      )}
    </div>
  );
}
