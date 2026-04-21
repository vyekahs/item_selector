'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import { ScoreBadge } from '@/components/ScoreBadge';
import { useProductList } from '@/lib/api/queries';
import {
  formatDecimalPct,
  formatKrw,
  formatScore,
} from '@/lib/utils/format';
import type { Channel } from '@/lib/api/types';

const PAGE_SIZE = 20;

const channelLabel: Record<Channel, string> = {
  SMARTSTORE: '스마트스토어',
  COUPANG: '쿠팡',
};

export default function HistoryPage() {
  const searchParams = useSearchParams();
  const keywordIdParam = searchParams.get('keyword_id');
  const keywordId = keywordIdParam ? Number(keywordIdParam) : null;
  const [page, setPage] = useState(0);
  const offset = page * PAGE_SIZE;
  const { data, isLoading, isError, error } = useProductList({
    limit: PAGE_SIZE,
    offset,
    keyword_id: keywordId,
  });

  const totalPages = useMemo(() => {
    if (!data) return 0;
    return Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  }, [data]);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">📒 입력 이력</h1>
          <p className="mt-1 text-sm text-slate-500">
            {keywordId != null
              ? `키워드 #${keywordId}에 등록된 상품만 표시`
              : '입력한 상품들의 채널별 점수·마진·ROI를 한눈에 비교합니다.'}
          </p>
        </div>
        {keywordId != null && (
          <Link href="/history" className="btn-secondary text-xs">
            전체 보기
          </Link>
        )}
      </header>

      {isLoading ? (
        <p role="status" className="text-sm text-slate-500">
          불러오는 중…
        </p>
      ) : isError ? (
        <p
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        >
          이력을 불러오지 못했습니다: {error.message}
        </p>
      ) : !data || data.items.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          아직 입력한 상품이 없습니다.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">상품</th>
                  <th className="py-2">단가/MOQ</th>
                  <th className="py-2">종합</th>
                  <th className="py-2">스마트스토어</th>
                  <th className="py-2">쿠팡</th>
                  <th className="py-2">추천</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => {
                  const score = p.latest_score;
                  const ss = score?.channel_profits.find(
                    (c) => c.channel === 'SMARTSTORE',
                  );
                  const cp = score?.channel_profits.find(
                    (c) => c.channel === 'COUPANG',
                  );
                  return (
                    <tr
                      key={p.id}
                      data-testid="history-row"
                      className="border-b border-slate-100 align-top"
                    >
                      <td className="py-2 pr-2">
                        <div className="font-medium text-slate-900">
                          {p.name ?? `상품 #${p.id}`}
                        </div>
                        <div className="text-xs text-slate-500">
                          {new Date(p.created_at).toLocaleDateString('ko-KR')}
                        </div>
                      </td>
                      <td className="py-2 pr-2 text-xs text-slate-600">
                        ¥{p.cny_price.toFixed(2)} · MOQ {p.moq}
                      </td>
                      <td className="py-2 pr-2">
                        {score ? (
                          <ScoreBadge
                            size="sm"
                            score={score.total_score}
                            recommendation={score.recommendation}
                          />
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-2 pr-2 tabular-nums">
                        {ss ? (
                          <div className="text-xs leading-tight">
                            <div>{formatKrw(ss.unit_profit_krw)}</div>
                            <div className="text-slate-500">
                              마진 {formatDecimalPct(ss.margin_pct)} · ROI{' '}
                              {formatDecimalPct(ss.roi_pct)}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-2 pr-2 tabular-nums">
                        {cp ? (
                          <div className="text-xs leading-tight">
                            <div>{formatKrw(cp.unit_profit_krw)}</div>
                            <div className="text-slate-500">
                              마진 {formatDecimalPct(cp.margin_pct)} · ROI{' '}
                              {formatDecimalPct(cp.roi_pct)}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-2 pr-2 text-xs">
                        {score?.recommended_channel
                          ? `🏆 ${channelLabel[score.recommended_channel]}`
                          : '—'}
                      </td>
                      <td className="py-2">
                        <Link
                          href={`/products/${p.id}`}
                          className="text-xs text-brand-600 hover:underline"
                        >
                          상세 →
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

          {/* score helper for sr-only label */}
          <span className="sr-only" data-testid="score-display">
            {data.items
              .map((p) => formatScore(p.latest_score?.total_score ?? null))
              .join(',')}
          </span>
        </>
      )}
    </div>
  );
}
