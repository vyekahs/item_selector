'use client';

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

export interface RadarScoreChartProps {
  opportunity: number;
  profit: number;
  risk: number;
  stability: number;
  /** Optional height; the chart always fills 100% width. */
  height?: number;
}

export function RadarScoreChart({
  opportunity,
  profit,
  risk,
  stability,
  height = 260,
}: RadarScoreChartProps) {
  const data = [
    { axis: '기회', value: Math.max(0, Math.min(100, opportunity)) },
    { axis: '수익', value: Math.max(0, Math.min(100, profit)) },
    { axis: '리스크', value: Math.max(0, Math.min(100, risk)) },
    { axis: '안정', value: Math.max(0, Math.min(100, stability)) },
  ];

  return (
    <div
      data-testid="radar-score-chart"
      className="w-full"
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="75%">
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 12 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
          <Radar
            name="점수"
            dataKey="value"
            stroke="#2b7fff"
            fill="#2b7fff"
            fillOpacity={0.35}
          />
          <Tooltip formatter={(v: number) => `${Math.round(v)}점`} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
