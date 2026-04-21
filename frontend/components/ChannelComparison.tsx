import { cn } from '@/lib/utils/cn';
import { formatDecimalPct, formatInt, formatKrw } from '@/lib/utils/format';
import type {
  Channel,
  ChannelProfitResponse,
} from '@/lib/api/types';

export interface ChannelComparisonProps {
  channels: ChannelProfitResponse[];
  recommendedChannel?: Channel | null;
  /** MOQ used to contextualise breakeven (purely informational). */
  moq?: number;
}

const channelLabel: Record<Channel, string> = {
  SMARTSTORE: '스마트스토어',
  COUPANG: '쿠팡',
};

interface Row {
  label: string;
  value: (channel: ChannelProfitResponse) => string;
  highlight?: boolean;
}

const rows: Row[] = [
  {
    label: '개당 원가',
    value: (c) => formatKrw(c.unit_cost_krw),
  },
  {
    label: '평균 판매가',
    value: (c) => formatKrw(c.expected_price_krw),
  },
  {
    label: '수수료',
    value: (c) => formatDecimalPct(c.platform_fee_pct),
  },
  {
    label: '광고비',
    value: (c) => formatDecimalPct(c.ad_cost_pct),
  },
  {
    label: '개당 순이익',
    value: (c) => formatKrw(c.unit_profit_krw),
    highlight: true,
  },
  {
    label: '마진율',
    value: (c) => formatDecimalPct(c.margin_pct),
    highlight: true,
  },
  {
    label: 'ROI',
    value: (c) => formatDecimalPct(c.roi_pct),
    highlight: true,
  },
  {
    label: '손익분기(월)',
    value: (c) => `${formatInt(c.breakeven_units)}개`,
  },
];

export function ChannelComparison({
  channels,
  recommendedChannel,
  moq,
}: ChannelComparisonProps) {
  if (!channels.length) {
    return (
      <p className="text-sm text-slate-500" data-testid="channel-empty">
        채널별 수익 데이터가 아직 없습니다.
      </p>
    );
  }

  const ordered = [...channels].sort((a, b) => {
    // Smart-store first, coupang second for a stable presentation
    if (a.channel === b.channel) return 0;
    return a.channel === 'SMARTSTORE' ? -1 : 1;
  });

  return (
    <div className="overflow-x-auto">
      {moq !== undefined ? (
        <p className="mb-2 text-xs text-slate-500">
          MOQ {formatInt(moq)}개 기준 · 손익분기는 월 판매량 기준
        </p>
      ) : null}
      <table className="w-full min-w-[480px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="py-2 text-left font-medium text-slate-500">항목</th>
            {ordered.map((c) => {
              const isRecommended = recommendedChannel === c.channel;
              return (
                <th
                  key={c.channel}
                  data-testid={`channel-header-${c.channel}`}
                  data-recommended={isRecommended ? 'true' : 'false'}
                  className={cn(
                    'py-2 text-right font-semibold',
                    isRecommended
                      ? 'text-brand-700'
                      : 'text-slate-700',
                  )}
                >
                  <span className="inline-flex items-center gap-1">
                    {isRecommended ? (
                      <span aria-label="추천 채널" title="추천 채널">
                        🏆
                      </span>
                    ) : null}
                    {channelLabel[c.channel]}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              className={cn(
                'border-b border-slate-100',
                row.highlight ? 'bg-slate-50/60' : null,
              )}
            >
              <th
                scope="row"
                className="py-2 text-left font-normal text-slate-600"
              >
                {row.label}
              </th>
              {ordered.map((c) => (
                <td
                  key={c.channel + row.label}
                  data-testid={`channel-cell-${c.channel}-${row.label}`}
                  className={cn(
                    'py-2 pl-4 text-right tabular-nums',
                    row.highlight ? 'font-semibold text-slate-900' : 'text-slate-700',
                    recommendedChannel === c.channel && row.highlight
                      ? 'text-brand-700'
                      : null,
                  )}
                >
                  {row.value(c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
