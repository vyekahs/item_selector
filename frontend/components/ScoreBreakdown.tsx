import type { OpportunityResponse } from '@/lib/api/types';
import { formatCompact } from '@/lib/utils/format';

export interface ScoreBreakdownProps {
  opportunity: OpportunityResponse;
}

function formatSignedPct(value: number | null | undefined): string {
  if (value == null) return '—';
  const rounded = Math.round(value * 10) / 10;
  const sign = rounded > 0 ? '+' : '';
  return `${sign}${rounded}%`;
}

function num(x: unknown, digits = 2): string {
  if (x == null || Number.isNaN(Number(x))) return '?';
  return Number(x).toFixed(digits);
}

/**
 * Collapsible "왜 이 점수가 나왔나" explainer for all 6 axes of the
 * opportunity score (기획서 §4.2).
 */
export function ScoreBreakdown({ opportunity }: ScoreBreakdownProps) {
  const d = (opportunity.score_details ?? {}) as Record<string, any>;
  const demand = d.demand ?? {};
  const growth = d.growth ?? {};
  const competition = d.competition ?? {};
  const customs = d.customs ?? {};
  const trend = d.trend ?? {};
  const stability = d.stability ?? {};

  return (
    <details className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <summary className="cursor-pointer font-medium text-slate-700">
        🔎 왜 이 점수가 나왔나? (6개 축 전체 설명)
      </summary>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {/* 1. Demand ------------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            📊 수요 크기{' '}
            <span className="text-slate-500">
              {opportunity.demand_score.toFixed(1)} / 25
            </span>{' '}
            <span className="text-emerald-700">· 높을수록 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            이 키워드가 네이버에서 월 몇 번이나 검색되는지. 수요 자체의 크기.
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          <p className="tabular-nums">
            log10(검색량 + 1) / log10(100,000 + 1) × 25
          </p>
          <p className="tabular-nums">
            = log10({formatCompact(demand.total_monthly_volume)} + 1) ÷ 5 × 25
            {' = '}
            <strong>{opportunity.demand_score.toFixed(1)}</strong>
          </p>
          <p className="text-[11px] text-slate-500">
            월 100K 이상이면 만점, 1K 근처면 약 7점, 100 근처면 약 3점.
          </p>
        </section>

        {/* 2. Growth ------------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            📈 수요 성장{' '}
            <span className="text-slate-500">
              {opportunity.growth_score.toFixed(1)} / 20
            </span>{' '}
            <span className="text-emerald-700">· +면 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            네이버 DataLab의 <strong>검색 트렌드 지표</strong>가 3개월 전 대비 얼마나
            변했는지. 지표는 "해당 키워드의 최근 12개월 중 최대치를 100으로 보는
            상대 인덱스"라서 절대 검색량이 아님. 계절성이 큰 키워드(쿨매트·우산·크리스마스)는
            비수기→수기 전환 시 수백 %까지 자연스럽게 찍힘.
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          <p className="tabular-nums">
            (최근 월 지표 − 3개월 전 월 지표) / 3개월 전 월 지표 × 100
          </p>
          <p className="tabular-nums">
            → 현재 <strong>{formatSignedPct(growth.growth_rate_3m_pct)}</strong>
          </p>
          <p className="mt-2 font-medium text-slate-700">점수 스케일</p>
          <p className="tabular-nums">
            (3m% + 10) / 60 × 20, −10%→0점, +50%→20점 → 현재{' '}
            <strong>{opportunity.growth_score.toFixed(1)}/20</strong>
          </p>
          <p className="mt-2 font-medium text-slate-700">해석 기준</p>
          <ul className="list-disc pl-4 text-[11px] text-slate-500">
            <li>
              <span className="font-medium text-amber-700">+300% 이상</span> —
              비수기→수기 전환 (계절성 큼, 재고 타이밍 주의. 사입 후 실제 수요기에
              출고되는지 꼭 체크)
            </li>
            <li>
              <span className="font-medium text-emerald-700">+50% ~ +300%</span>{' '}
              — 실질 상승세 (시장 확대 중, 진입 타이밍 좋음)
            </li>
            <li>
              <span className="font-medium text-slate-600">−20% ~ +50%</span> —
              꾸준함 (성숙 시장, 차별화 필요)
            </li>
            <li>
              <span className="font-medium text-rose-700">−20% 이하</span> —
              식는 중 (진입 비권장)
            </li>
          </ul>
        </section>

        {/* 3. Competition ------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            🎯 경쟁 공백 (블루오션){' '}
            <span className="text-slate-500">
              {opportunity.competition_score.toFixed(1)} / 20
            </span>{' '}
            <span className="text-emerald-700">· 높을수록 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            수요 있는데 경쟁자가 얼마나 적은가. 14+ 낮은 경쟁 / 7~14 중간 / 7−
            레드오션.
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          <p className="tabular-nums">
            (1 − 경쟁지수) × 검색량가중 × 쇼핑과포화감점 × 20
          </p>
          <p className="tabular-nums">
            = (1 − {num(competition.competition_index)}) ×{' '}
            {num(competition.demand_factor)} ×{' '}
            {num(
              competition.vacancy != null &&
                competition.competition_index != null &&
                1 - Number(competition.competition_index) > 0
                ? Number(competition.vacancy) /
                    (1 - Number(competition.competition_index))
                : null,
            )}
            {' × 20 = '}
            <strong>{opportunity.competition_score.toFixed(1)}</strong>
          </p>
          <ul className="mt-1 list-disc pl-4 text-[11px] text-slate-500">
            <li>
              경쟁지수: 네이버 검색광고가 주는 값 (0.2=낮음, 0.5=중간, 0.8=높음)
            </li>
            <li>
              검색량가중: 1K미만=0, 10K+이면 1.0. 현재 쇼핑 상품수{' '}
              <strong>{formatCompact(competition.shopping_total_count)}</strong>개
            </li>
            <li>쇼핑과포화감점: 500K+이면 0.7, 200K+이면 0.85, 그 외 1.0</li>
          </ul>
        </section>

        {/* 4. Customs ----------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            📦 중국 수입 실체{' '}
            <span className="text-slate-500">
              {opportunity.customs_score.toFixed(1)} / 20
            </span>{' '}
            <span className="text-emerald-700">· +면 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            관세청 통관 기준 "실제로 중국에서 한국으로 수입이 늘고 있는지". 검색만
            뜨고 수입은 줄면 거품일 수 있음.
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          {customs.reason === 'no_customs_data' ? (
            <p className="text-[11px] text-slate-500">
              해당 HS코드 수입 데이터 없음 → 중립 10점 부여.
            </p>
          ) : (
            <>
              <p className="tabular-nums">
                (3m성장% + 30) / 60 × 20, 대칭 스케일
              </p>
              <p className="tabular-nums">
                = ({formatSignedPct(customs.growth_rate_3m_pct)} + 30) ÷ 60 × 20
                {' = '}
                <strong>{opportunity.customs_score.toFixed(1)}</strong>
              </p>
              <p className="text-[11px] text-slate-500">
                −30%→0점, 0%→10점(중립), +30%→20점. 평탄해도 불이익 없음(성숙 시장).
              </p>
            </>
          )}
        </section>

        {/* 5. Trend ------------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            🔥 트렌드 선행{' '}
            <span className="text-slate-500">
              {opportunity.trend_score.toFixed(1)} / 10
            </span>{' '}
            <span className="text-emerald-700">· 높을수록 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            유튜브 리뷰 영상 증가율 + 블로그/카페 포스팅 증가율 평균. 검색량 급등
            전에 뜨는 선행 신호.
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          {trend.reason === 'no_leading_signals' ? (
            <p className="text-[11px] text-slate-500">
              유튜브/블로그 신호 둘 다 없음 → 중립 5점.
            </p>
          ) : (
            <>
              <p className="tabular-nums">
                평균(YT, 블로그 30일 성장) → −50%→0점, +200%→10점 (선형)
              </p>
              <p className="tabular-nums text-[11px]">
                YT:{' '}
                {trend.youtube_growth_30d_clamped != null ? (
                  <>
                    {formatSignedPct(Number(trend.youtube_growth_30d_clamped) * 100)}
                    {trend.youtube_growth_30d_raw !==
                      trend.youtube_growth_30d_clamped &&
                    trend.youtube_growth_30d_raw != null ? (
                      <>
                        {' '}
                        (원본{' '}
                        {formatSignedPct(
                          Number(trend.youtube_growth_30d_raw) * 100,
                        )}
                        , 캡 ±200%)
                      </>
                    ) : null}
                  </>
                ) : (
                  <span className="text-amber-700">
                    데이터 없음 (YouTube API 쿼터 소진 또는 수집 실패 → 블로그만으로 계산)
                  </span>
                )}
                {' · 블로그: '}
                {trend.blog_growth_30d_clamped != null
                  ? formatSignedPct(Number(trend.blog_growth_30d_clamped) * 100)
                  : '—'}
              </p>
              <p className="tabular-nums">
                평균{' '}
                {formatSignedPct(
                  trend.avg_growth_decimal != null
                    ? Number(trend.avg_growth_decimal) * 100
                    : null,
                )}
                {' → '}
                <strong>{opportunity.trend_score.toFixed(1)}</strong>
              </p>
              <p className="text-[11px] text-slate-500">
                ±200%로 cap — 과거 데이터 0일 때 튀는 값 보정. YT/블로그 중
                하나만 있으면 있는 쪽으로만 평균.
              </p>
            </>
          )}
        </section>

        {/* 6. Stability --------------------------------------------- */}
        <section>
          <h4 className="font-semibold text-slate-800">
            🛡️ 안정성{' '}
            <span className="text-slate-500">
              {opportunity.stability_score.toFixed(1)} / 5
            </span>{' '}
            <span className="text-emerald-700">· 높을수록 좋음</span>
          </h4>
          <p className="mt-1 text-slate-600">
            연중 판매 꾸준한지 (1.0 = 평탄, 3.5 이상 = 특정 시즌 외 재고 부담).
          </p>
          <p className="mt-2 font-medium text-slate-700">계산식</p>
          <p className="tabular-nums">
            5 − (계절성지수 − 1) × 2, 최소 0
          </p>
          <p className="tabular-nums">
            계절성 {num(stability.seasonality_index, 2)} ={' '}
            <strong>{opportunity.stability_score.toFixed(1)}</strong>
          </p>
          <p className="text-[11px] text-slate-500">
            현재는 계절성 자동 감지 미구현 — 1.0 고정 (모든 키워드 5점).
            Phase 4에서 DataLab 12개월 추세 기반으로 자동 산출 예정.
          </p>
        </section>
      </div>
    </details>
  );
}
