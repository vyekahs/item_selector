import Link from 'next/link';

import type { OpportunityResponse } from '@/lib/api/types';
import { formatCompact, formatKrw } from '@/lib/utils/format';
import { ScoreBadge } from './ScoreBadge';
import { ScoreBreakdown } from './ScoreBreakdown';

export interface OpportunityRowProps {
  opportunity: OpportunityResponse;
}

function formatSignedPct(value: number | null | undefined): string {
  if (value == null) return '—';
  const rounded = Math.round(value * 10) / 10;
  const sign = rounded > 0 ? '+' : '';
  return `${sign}${rounded}%`;
}

function competitionColorClass(score: number | null | undefined): string {
  if (score == null) return 'text-slate-500';
  if (score >= 14) return 'text-emerald-700';
  if (score >= 7) return 'text-amber-700';
  return 'text-rose-700';
}

function customsColorClass(pct: number | null | undefined): string {
  if (pct == null) return 'text-slate-500';
  if (pct >= 10) return 'text-emerald-700';
  if (pct <= -10) return 'text-rose-700';
  return 'text-slate-600';
}

const EXCLUSION_REASON_LABELS: Record<string, string> = {
  imports_declining: '중국 수입이 최근 심각하게 감소 중 (3개월 평균 −30% 이하)',
  certification_required: 'KC/전안법/식약처 등 인증 필수 카테고리',
  seasonality_too_high: '계절성 과도 (비수기 재고 부담)',
  redocean_reviews: '레드오션 — 상위 경쟁사 평균 리뷰 1,000개 이상',
  insufficient_demand: '월 검색량 500회 미만 — 실질 수요 없음',
};

function translateExclusionReason(code: string): string {
  return EXCLUSION_REASON_LABELS[code] ?? code;
}

export function OpportunityRow({ opportunity }: OpportunityRowProps) {
  const m = opportunity.metrics;
  const productNewHref = `/products/new?keyword_id=${opportunity.keyword_id}&term=${encodeURIComponent(
    opportunity.term,
  )}`;

  return (
    <article
      data-testid="opportunity-row"
      className="card flex flex-col gap-3"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white"
            aria-label={`${opportunity.rank}위`}
          >
            {opportunity.rank}
          </span>
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              {opportunity.term}
            </h3>
            {opportunity.category_name ? (
              <p className="text-xs text-slate-500">
                {opportunity.category_name}
              </p>
            ) : null}
          </div>
        </div>
        <ScoreBadge score={opportunity.total_score} />
      </header>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-3 text-sm text-slate-600 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-slate-400">월 검색량</dt>
          <dd className="tabular-nums">{formatCompact(m.monthly_search_volume)}</dd>
          <dd className="text-[10px] text-slate-400">네이버 PC+모바일 합산</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">검색 3개월 성장</dt>
          <dd className="tabular-nums">{formatSignedPct(m.search_growth_3m)}</dd>
          <dd className="text-[10px] text-slate-400">+면 뜨는 중 / −면 식는 중</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">경쟁공백 (블루오션)</dt>
          <dd
            className={`tabular-nums font-medium ${competitionColorClass(
              m.competition_raw_score,
            )}`}
            data-testid="competition-score"
          >
            {m.competition_raw_score != null
              ? `${m.competition_raw_score.toFixed(1)} / 20`
              : '—'}
          </dd>
          <dd className="text-[10px] text-slate-400">
            <span className="text-emerald-600">높을수록 좋음</span> · 20=무경쟁
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">중국 수입 3개월</dt>
          <dd
            className={`tabular-nums font-medium ${customsColorClass(
              m.customs_growth_3m_pct,
            )}`}
            data-testid="customs-growth"
          >
            {formatSignedPct(m.customs_growth_3m_pct)}
          </dd>
          <dd className="text-[10px] text-slate-400">
            <span className="text-emerald-600">+면 수요↑</span> /{' '}
            <span className="text-rose-600">−면 수요↓</span>
          </dd>
        </div>
      </dl>

      <ScoreBreakdown opportunity={opportunity} />


      <p className="text-sm text-slate-600">
        스마트스토어 평균가{' '}
        <span className="font-medium text-slate-800">
          {formatKrw(m.smartstore_avg_price_krw)}
        </span>
        {m.coupang_avg_price_krw != null && (
          <>
            {' '}· 쿠팡 평균가{' '}
            <span className="font-medium text-slate-800">
              {formatKrw(m.coupang_avg_price_krw)}
            </span>
          </>
        )}
      </p>

      {opportunity.is_excluded ? (
        <div
          data-testid="opportunity-excluded"
          className="rounded bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          <p className="font-medium">🚫 자동 제외됨</p>
          {opportunity.exclusion_reasons ? (
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {opportunity.exclusion_reasons.split(',').map((reason) => (
                <li key={reason}>{translateExclusionReason(reason.trim())}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <footer className="flex flex-wrap items-center gap-2">
        <a
          href={opportunity.search_1688_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary"
          data-testid="search-1688-link"
        >
          1688에서 찾기 →
        </a>
        <Link
          href={productNewHref}
          className="btn-primary"
          data-testid="input-product-link"
        >
          상품 입력
        </Link>
        {opportunity.product_count > 0 && (
          <Link
            href={`/history?keyword_id=${opportunity.keyword_id}`}
            className="btn-secondary"
            data-testid="product-history-link"
          >
            📦 등록된 상품 {opportunity.product_count}개
          </Link>
        )}
      </footer>
    </article>
  );
}
