'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';

import { ChannelComparison } from '@/components/ChannelComparison';
import { CostBreakdown } from '@/components/CostBreakdown';
import { FeedbackForm } from '@/components/FeedbackForm';
import { RadarScoreChart } from '@/components/RadarScoreChart';
import { ScoreBadge } from '@/components/ScoreBadge';
import { useProduct } from '@/lib/api/queries';
import type { Channel, ProductScoreResponse } from '@/lib/api/types';

const channelLabel: Record<Channel, string> = {
  SMARTSTORE: '스마트스토어',
  COUPANG: '쿠팡',
};

export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const productId = Number(params?.id);
  const { data, isLoading, isError, error } = useProduct(productId);

  if (Number.isNaN(productId)) {
    return <p className="text-rose-600">잘못된 상품 id 입니다.</p>;
  }
  if (isLoading) {
    return <p role="status" className="text-sm text-slate-500">불러오는 중…</p>;
  }
  if (isError) {
    return (
      <p
        role="alert"
        className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
      >
        상품을 불러오지 못했습니다: {error.message}
      </p>
    );
  }
  if (!data) return null;

  const score: ProductScoreResponse | null = data.latest_score;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            {data.name ?? `상품 #${data.id}`}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 hover:underline"
            >
              1688 원본 보기 ↗
            </a>
            <span className="ml-2">단가 ¥{data.cny_price.toFixed(2)}</span>
            <span className="ml-2">MOQ {data.moq}개</span>
          </p>
        </div>
        {score ? (
          <ScoreBadge
            size="lg"
            score={score.total_score}
            recommendation={score.recommendation}
          />
        ) : null}
      </header>

      {score ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section
            data-testid="radar-section"
            className="card flex flex-col gap-2"
          >
            <h2 className="text-sm font-semibold text-slate-700">
              종합 점수 (레이더)
            </h2>
            <RadarScoreChart
              opportunity={score.opportunity_score}
              profit={score.profit_score}
              risk={score.risk_score}
              stability={score.stability_score}
            />
            <dl className="grid grid-cols-4 gap-1 text-center text-xs text-slate-600">
              <div>
                <dt>기회</dt>
                <dd className="font-semibold text-slate-900">
                  {Math.round(score.opportunity_score)}
                </dd>
              </div>
              <div>
                <dt>수익</dt>
                <dd className="font-semibold text-slate-900">
                  {Math.round(score.profit_score)}
                </dd>
              </div>
              <div>
                <dt>리스크</dt>
                <dd className="font-semibold text-slate-900">
                  {Math.round(score.risk_score)}
                </dd>
              </div>
              <div>
                <dt>안정</dt>
                <dd className="font-semibold text-slate-900">
                  {Math.round(score.stability_score)}
                </dd>
              </div>
            </dl>
          </section>

          <CostBreakdown
            breakdown={score.cost_breakdown}
            productId={data.id}
            currentMoq={data.moq}
            currentAdCostPct={score.channel_profits[0]?.ad_cost_pct ?? 0.10}
          />

          <section className="card flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-slate-700">
              채널별 수익 비교
            </h2>
            <ChannelComparison
              channels={score.channel_profits}
              recommendedChannel={score.recommended_channel}
              moq={data.moq}
            />
            {score.recommended_channel ? (
              <p
                data-testid="recommended-channel"
                className="rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-700"
              >
                🏆 추천 채널:{' '}
                <strong>{channelLabel[score.recommended_channel]}</strong>
              </p>
            ) : (
              <p className="text-xs text-slate-500">
                추천 채널이 결정되지 않았습니다 (데이터 부족 또는 동률).
              </p>
            )}
          </section>
        </div>
      ) : (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          아직 점수 스냅샷이 없습니다.
        </p>
      )}

      {data.score_history.length > 1 ? (
        <section className="card">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">
            점수 이력
          </h2>
          <ul className="space-y-1 text-sm text-slate-700">
            {data.score_history.map((s) => (
              <li
                key={`${s.snapshot_date}-${s.product_id}`}
                className="flex justify-between border-b border-slate-100 py-1 last:border-0"
              >
                <span>{s.snapshot_date}</span>
                <span className="tabular-nums">
                  {s.total_score.toFixed(1)} · {s.recommendation}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <FeedbackForm productId={data.id} />

      <div>
        <Link href="/history" className="text-sm text-brand-600 hover:underline">
          ← 이력으로 돌아가기
        </Link>
      </div>
    </div>
  );
}
