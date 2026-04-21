import { cn } from '@/lib/utils/cn';
import type { Recommendation } from '@/lib/api/types';

export interface ScoreBadgeProps {
  score: number;
  /** Optional recommendation label; when omitted only the score pill is rendered. */
  recommendation?: Recommendation;
  /** Display size. */
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function scoreTier(
  score: number,
): 'excellent' | 'good' | 'ok' | 'warn' | 'bad' {
  if (score >= 85) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 55) return 'ok';
  if (score >= 40) return 'warn';
  return 'bad';
}

const tierClasses: Record<ReturnType<typeof scoreTier>, string> = {
  excellent: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300',
  good: 'bg-lime-100 text-lime-800 ring-1 ring-lime-300',
  ok: 'bg-amber-100 text-amber-800 ring-1 ring-amber-300',
  warn: 'bg-orange-100 text-orange-800 ring-1 ring-orange-300',
  bad: 'bg-rose-100 text-rose-800 ring-1 ring-rose-300',
};

const recommendationClasses: Record<Recommendation, string> = {
  GO: 'bg-emerald-600 text-white',
  CONDITIONAL: 'bg-amber-500 text-white',
  PASS: 'bg-rose-600 text-white',
};

const recommendationLabel: Record<Recommendation, string> = {
  GO: '✅ GO',
  CONDITIONAL: '⚠️ 조건부',
  PASS: '🛑 PASS',
};

const sizeClasses: Record<NonNullable<ScoreBadgeProps['size']>, string> = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-2.5 py-1',
  lg: 'text-base px-3 py-1.5',
};

export function ScoreBadge({
  score,
  recommendation,
  size = 'md',
  className,
}: ScoreBadgeProps) {
  const tier = scoreTier(score);
  const rounded = Math.round(score);

  return (
    <div
      className={cn('inline-flex items-center gap-2 font-medium', className)}
    >
      <span
        data-testid="score-pill"
        data-tier={tier}
        className={cn(
          'inline-flex items-center rounded-full font-semibold',
          tierClasses[tier],
          sizeClasses[size],
        )}
        aria-label={`종합 점수 ${rounded}점`}
      >
        {rounded}점
      </span>
      {recommendation ? (
        <span
          data-testid="recommendation-pill"
          data-recommendation={recommendation}
          className={cn(
            'inline-flex items-center rounded-md font-semibold',
            recommendationClasses[recommendation],
            sizeClasses[size],
          )}
        >
          {recommendationLabel[recommendation]}
        </span>
      ) : null}
    </div>
  );
}
