'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import { API_BASE_URL } from '@/lib/api/client';
import { useDetailPage } from '@/lib/api/queries';
import { useRegenerateDetailPage } from '@/lib/api/mutations';
import type { DetailPageStatus } from '@/lib/api/types';

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
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${statusBadgeClass[status]}`}
    >
      {statusLabel[status]}
    </span>
  );
}

export default function DetailPageDetailRoute() {
  const params = useParams<{ id: string }>();
  const detailPageId = Number(params?.id);
  const { data, isLoading, isError, error } = useDetailPage(
    Number.isFinite(detailPageId) ? detailPageId : null,
  );
  const regenerate = useRegenerateDetailPage();
  const [flash, setFlash] = useState<string | null>(null);

  if (Number.isNaN(detailPageId)) {
    return <p className="text-rose-600">잘못된 detail page id 입니다.</p>;
  }

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-slate-500">
        불러오는 중…
      </p>
    );
  }

  if (isError) {
    return (
      <p
        role="alert"
        className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
      >
        상세페이지를 불러오지 못했습니다: {error.message}
      </p>
    );
  }
  if (!data) return null;

  const isProcessing =
    data.status === 'pending' || data.status === 'processing';
  const imageUrl =
    data.image_path && data.status === 'done'
      ? `${API_BASE_URL}/generated/${data.image_path}`
      : null;

  const handleRegenerate = async () => {
    setFlash(null);
    try {
      await regenerate.mutateAsync(data.id);
      setFlash('🔄 재생성을 시작했습니다. 1~2분 후 자동으로 갱신됩니다.');
    } catch (err) {
      setFlash(
        `❌ 재생성 실패: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-slate-900">
            {data.title_ko ?? `상세페이지 #${data.id}`}
          </h1>
          <p className="text-sm text-slate-500">
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 hover:underline"
              title={data.source_url}
            >
              {data.source_platform} 원본 보기 ↗
            </a>
            <span className="ml-2 text-xs text-slate-400">
              생성일 {new Date(data.created_at).toLocaleString('ko-KR')}
            </span>
          </p>
        </div>
        <StatusBadge status={data.status} />
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary"
          onClick={handleRegenerate}
          disabled={regenerate.isPending || isProcessing}
          title={
            isProcessing
              ? '진행 중일 때는 재생성할 수 없습니다.'
              : '파이프라인을 처음부터 다시 실행합니다.'
          }
        >
          {regenerate.isPending ? '재생성 요청 중…' : '🔄 다시 생성'}
        </button>
        {imageUrl && (
          <a
            href={imageUrl}
            download={`detail-page-${data.id}.jpg`}
            className="btn-secondary"
          >
            📥 이미지 다운로드
          </a>
        )}
        <Link href="/detail-pages" className="btn-secondary">
          ← 목록으로
        </Link>
      </div>

      {flash && (
        <p
          role="status"
          className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          {flash}
        </p>
      )}

      {isProcessing && (
        <section className="card flex items-center gap-3">
          <span
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-sky-300 border-t-sky-600"
            aria-hidden="true"
          />
          <p className="text-sm text-slate-700">
            처리 중… 이미지 다운로드 → OCR → LLM 카피라이팅 → 렌더링까지 1~2분
            소요됩니다. 페이지는 5초마다 자동으로 새로고침됩니다.
          </p>
        </section>
      )}

      {data.status === 'failed' && (
        <section className="rounded-md border border-rose-200 bg-rose-50 p-4">
          <h2 className="mb-2 text-sm font-semibold text-rose-700">
            ❌ 생성 실패
          </h2>
          <pre className="whitespace-pre-wrap rounded border border-rose-200 bg-white p-3 text-xs text-rose-800">
            {data.failure_reason ?? '(원인 정보 없음)'}
          </pre>
        </section>
      )}

      {imageUrl && (
        <section className="card flex flex-col items-center gap-2">
          <h2 className="self-start text-sm font-semibold text-slate-700">
            🖼️ 렌더 결과 (가로 860px)
          </h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl}
            alt={`상세페이지 ${data.id} 미리보기`}
            className="max-w-full rounded border border-slate-200 shadow-sm"
            style={{ maxWidth: 860 }}
          />
        </section>
      )}

      {data.props && (
        <section className="card">
          <details>
            <summary className="cursor-pointer text-sm font-semibold text-slate-700">
              🔍 Props (LLM 산출물 + 템플릿 바인딩 데이터)
            </summary>
            <pre className="mt-3 max-h-[480px] overflow-auto rounded bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
              {JSON.stringify(data.props, null, 2)}
            </pre>
          </details>
        </section>
      )}
    </div>
  );
}
