'use client';

import { FormEvent, useState } from 'react';

import { ChannelComparison } from '@/components/ChannelComparison';
import { CostBreakdown } from '@/components/CostBreakdown';
import { apiRequest } from '@/lib/api/client';
import { useCategories } from '@/lib/api/queries';
import type {
  Channel,
  ChannelProfitResponse,
  CostBreakdownResponse,
} from '@/lib/api/types';

interface CalculatorResult {
  cost_breakdown: CostBreakdownResponse;
  channel_profits: ChannelProfitResponse[];
  recommended_channel: Channel | null;
}

export default function CalculatorPage() {
  const categoriesQuery = useCategories();
  const [cnyPrice, setCnyPrice] = useState('');
  const [moq, setMoq] = useState('100');
  const [sellPrice, setSellPrice] = useState('');
  const [categoryName, setCategoryName] = useState('반려동물');
  const [chinaShippingKrw, setChinaShippingKrw] = useState('0');
  const [unitWeight, setUnitWeight] = useState('');
  const [intlShipping, setIntlShipping] = useState('');
  const [dutyPct, setDutyPct] = useState('8');
  const [adPct, setAdPct] = useState('10');
  const [result, setResult] = useState<CalculatorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const weight = Number(unitWeight);
      const intl = Number(intlShipping);
      const payload: Record<string, unknown> = {
        cny_price: Number(cnyPrice),
        moq: Number(moq),
        expected_sell_price_krw: Number(sellPrice),
        category_name: categoryName,
        china_domestic_shipping_krw: Number(chinaShippingKrw) || 0,
        customs_duty_pct: (Number(dutyPct) || 0) / 100,
        ad_cost_pct: (Number(adPct) || 0) / 100,
      };
      if (Number.isFinite(weight) && weight > 0) {
        payload.unit_weight_kg = weight;
      } else if (Number.isFinite(intl) && intl > 0) {
        payload.intl_shipping_krw = intl;
      } else {
        throw new Error('무게(kg) 또는 국제 배송비 중 하나는 입력해주세요.');
      }
      const res = await apiRequest<CalculatorResult>('/calculator', {
        method: 'POST',
        body: payload,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const categories = categoriesQuery.data?.roots ?? [];

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-xl font-bold text-slate-900">🧮 원가·마진 계산기</h1>
        <p className="mt-1 text-sm text-slate-500">
          상품 저장 없이 수입 원가 + 채널별 수익만 즉시 계산합니다. 추천
          리스트에 없는 키워드도 자유롭게 시뮬레이션 가능.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="card flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">CNY 단가 (¥)</span>
            <input
              type="number"
              step="0.01"
              min={0}
              className="input"
              value={cnyPrice}
              onChange={(e) => setCnyPrice(e.target.value)}
              required
              placeholder="예: 28"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">MOQ</span>
            <input
              type="number"
              min={1}
              className="input"
              value={moq}
              onChange={(e) => setMoq(e.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">예상 판매가 (KRW)</span>
            <input
              type="number"
              min={0}
              className="input"
              value={sellPrice}
              onChange={(e) => setSellPrice(e.target.value)}
              required
              placeholder="예: 38000"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">카테고리</span>
            <select
              className="input"
              value={categoryName}
              onChange={(e) => setCategoryName(e.target.value)}
            >
              {categories.length === 0 && <option value="반려동물">반려동물</option>}
              {categories.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">중국 국내 배송 (KRW)</span>
            <input
              type="number"
              min={0}
              className="input"
              value={chinaShippingKrw}
              onChange={(e) => setChinaShippingKrw(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">개당 무게 (kg)</span>
            <input
              type="number"
              step="0.01"
              min={0}
              className="input"
              value={unitWeight}
              onChange={(e) => setUnitWeight(e.target.value)}
              placeholder="입력 시 자동 요율 계산"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">국제 배송 (KRW, 수동)</span>
            <input
              type="number"
              min={0}
              className="input"
              value={intlShipping}
              onChange={(e) => setIntlShipping(e.target.value)}
              disabled={Number(unitWeight) > 0}
              placeholder="무게 미입력 시 직접 입력"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">관세율 (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              className="input"
              value={dutyPct}
              onChange={(e) => setDutyPct(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">광고비 (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step="0.5"
              className="input"
              value={adPct}
              onChange={(e) => setAdPct(e.target.value)}
            />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-sm text-rose-600">
            {error}
          </p>
        )}
        <div className="flex justify-end">
          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
          >
            {loading ? '계산 중…' : '🧮 계산하기'}
          </button>
        </div>
      </form>

      {result && (
        <>
          <CostBreakdown breakdown={result.cost_breakdown} />
          <ChannelComparison
            channels={result.channel_profits}
            recommendedChannel={result.recommended_channel}
          />
        </>
      )}
    </div>
  );
}
