'use client';

import { FormEvent, useState } from 'react';

import type { CostBreakdownResponse } from '@/lib/api/types';
import { formatDecimalPct, formatKrw } from '@/lib/utils/format';
import { useUpdateProductCosts } from '@/lib/api/mutations';

export interface CostBreakdownProps {
  breakdown: CostBreakdownResponse | null | undefined;
  /** Passing productId enables inline editing via PATCH /products/{id}. */
  productId?: number;
  /** Shown as the MOQ default so user doesn't have to re-type it. */
  currentMoq?: number;
  /** Current ad cost pct (decimal). Defaults to 0.10 if unknown. */
  currentAdCostPct?: number;
}

/**
 * Full landed-cost decomposition + inline editor for the three user-
 * controllable inputs (MOQ, 중국 국내 배송비, 국제 배송비). Everything
 * else (관세 / 부가세 / 수입신고) is derived.
 *
 * When ``mokrok_duty_free`` is true (CIF under USD 150) the duty / VAT /
 * filing rows render as "면세" with a short explanation of why.
 */
export function CostBreakdown({
  breakdown,
  productId,
  currentMoq,
  currentAdCostPct,
}: CostBreakdownProps) {
  const [editing, setEditing] = useState(false);

  if (!breakdown) return null;

  return editing && productId != null ? (
    <EditForm
      productId={productId}
      initialMoq={currentMoq ?? breakdown.moq}
      initialChinaShippingKrw={breakdown.china_domestic_shipping_krw}
      initialIntlShipping={breakdown.intl_shipping_krw}
      initialDutyPct={breakdown.effective_duty_pct}
      initialSellPrice={breakdown.expected_sell_price_krw ?? 0}
      naverAvgPrice={breakdown.naver_avg_price_krw}
      initialAdPct={currentAdCostPct ?? 0.10}
      initialWeightKg={breakdown.total_weight_kg != null && breakdown.moq > 0 ? breakdown.total_weight_kg / breakdown.moq : 0}
      initialShippingMethod={breakdown.shipping_method_applied ?? null}
      intlShippingSource={breakdown.intl_shipping_source ?? null}
      suggestedBaseDutyPct={breakdown.suggested_base_duty_pct}
      suggestedKcftaDutyPct={breakdown.suggested_kcfta_duty_pct}
      exchangeRateCnyKrw={breakdown.exchange_rate_cny_krw}
      onCancel={() => setEditing(false)}
      onSaved={() => setEditing(false)}
    />
  ) : (
    <ReadonlyView
      breakdown={breakdown}
      onEdit={productId != null ? () => setEditing(true) : undefined}
    />
  );
}

// ---------------------------------------------------------------- view

function ReadonlyView({
  breakdown,
  onEdit,
}: {
  breakdown: CostBreakdownResponse;
  onEdit?: () => void;
}) {
  const {
    moq,
    goods_cost_krw,
    china_domestic_shipping_krw,
    intl_shipping_krw,
    cif_krw,
    cif_usd_approx,
    customs_duty_krw,
    vat_krw,
    filing_fee_krw,
    mokrok_duty_free,
    total_cost_krw,
    unit_cost_krw,
    effective_duty_pct,
    effective_vat_pct,
    shipping_method_applied,
    total_weight_kg,
    intl_shipping_source,
  } = breakdown;

  const intlNote = (() => {
    if (intl_shipping_source === 'rate_table' && shipping_method_applied) {
      const methodLabel =
        shipping_method_applied === 'lcl' ? 'LCL해운' : '해운(자가)';
      const weightLabel =
        total_weight_kg != null ? ` · 총 ${total_weight_kg}kg` : '';
      return `${methodLabel} (협력사)${weightLabel}`;
    }
    return '중국 → 한국';
  })();

  const rows: {
    label: string;
    value: string;
    note?: string;
    strong?: boolean;
    editable?: boolean;
  }[] = [
    {
      label: '① 상품 원가',
      value: formatKrw(goods_cost_krw),
      note: `CNY × MOQ ${moq}개 × 환율`,
    },
    {
      label: '② 중국 국내 배송 ✏️',
      value: formatKrw(china_domestic_shipping_krw),
      note: '공장 → 배송대행지',
      editable: true,
    },
    {
      label: '③ 국제 배송 ✏️',
      value: formatKrw(intl_shipping_krw),
      note: intlNote,
      editable: true,
    },
    {
      label: 'CIF (①+②+③)',
      value: `${formatKrw(cif_krw)} (≈ $${cif_usd_approx.toFixed(0)})`,
      note: '관세 과표',
      strong: true,
    },
    {
      label: '④ 관세',
      value: `${formatKrw(customs_duty_krw)} (${formatDecimalPct(effective_duty_pct)})`,
      note:
        breakdown.duty_source === 'hs_lookup'
          ? 'HS코드 자동 조회 기본관세'
          : breakdown.duty_source === 'user_override'
            ? '사용자 지정'
            : 'CIF × 관세율',
    },
    {
      label: '⑤ 부가세',
      value: `${formatKrw(vat_krw)} (${formatDecimalPct(effective_vat_pct)})`,
      note: '(CIF + 관세) × 10%',
    },
    {
      label: '⑥ 수입신고 수수료',
      value: formatKrw(filing_fee_krw),
      note: '관세사 대행 1회 (30,000원)',
    },
    {
      label: '총 수입 원가',
      value: formatKrw(total_cost_krw),
      note: `MOQ ${moq}개 기준`,
      strong: true,
    },
    {
      label: '개당 원가',
      value: formatKrw(unit_cost_krw),
      note: '총원가 ÷ MOQ',
      strong: true,
    },
  ];

  return (
    <section className="card">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">수입 원가 내역</h2>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            정식 수입 (판매 목적)
          </span>
          {onEdit && (
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={onEdit}
            >
              ✏️ 수정
            </button>
          )}
        </div>
      </header>

      <p className="mb-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
        💡 <strong>판매 목적 수입은 목록통관 면세 대상이 아님</strong>.
        CIF 금액과 무관하게 관세(CIF × 관세율) + 부가세((CIF+관세) × 10%) +
        수입신고 수수료(30,000원)가 항상 부과됩니다.
        {mokrok_duty_free && ' (DB에 저장된 예전 면세 플래그는 무시됩니다.)'}
      </p>

      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              className={
                row.strong
                  ? 'border-t border-slate-300 bg-slate-50 font-semibold text-slate-900'
                  : 'border-t border-slate-100 text-slate-700'
              }
            >
              <td className="py-1.5 pr-3">{row.label}</td>
              <td className="py-1.5 text-right tabular-nums">{row.value}</td>
              <td className="py-1.5 pl-3 text-right text-xs text-slate-400">
                {row.note ?? ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ---------------------------------------------------------------- edit form

function EditForm({
  productId,
  initialMoq,
  initialChinaShippingKrw,
  initialIntlShipping,
  initialDutyPct,
  initialSellPrice,
  naverAvgPrice,
  initialAdPct,
  initialWeightKg,
  initialShippingMethod,
  intlShippingSource,
  suggestedBaseDutyPct,
  suggestedKcftaDutyPct,
  exchangeRateCnyKrw,
  onCancel,
  onSaved,
}: {
  productId: number;
  initialMoq: number;
  initialChinaShippingKrw: number;
  initialIntlShipping: number;
  initialDutyPct: number;
  initialSellPrice: number;
  naverAvgPrice: number | null;
  initialAdPct: number;
  initialWeightKg: number;
  initialShippingMethod: string | null;
  intlShippingSource: string | null;
  suggestedBaseDutyPct: number | null;
  suggestedKcftaDutyPct: number | null;
  exchangeRateCnyKrw: number;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const mutation = useUpdateProductCosts(productId);
  const [moq, setMoq] = useState(String(initialMoq));
  const initialChinaCny =
    initialChinaShippingKrw > 0 && exchangeRateCnyKrw > 0
      ? (initialChinaShippingKrw / exchangeRateCnyKrw).toFixed(2)
      : '0';
  const [chinaCny, setChinaCny] = useState(initialChinaCny);
  const [intl, setIntl] = useState(String(initialIntlShipping));
  const [dutyPct, setDutyPct] = useState(String((initialDutyPct * 100).toFixed(1)));
  const [sellPrice, setSellPrice] = useState(String(initialSellPrice || ''));
  const [adPct, setAdPct] = useState(String((initialAdPct * 100).toFixed(1)));
  const [weightKg, setWeightKg] = useState(
    initialWeightKg > 0 ? initialWeightKg.toFixed(3) : '',
  );
  const [shippingMethod, setShippingMethod] = useState(
    initialShippingMethod ?? 'auto',
  );

  const chinaCnyNum = Number(chinaCny) || 0;
  const chinaKrwPreview = Math.max(0, Math.round(chinaCnyNum * exchangeRateCnyKrw));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const dutyNumber = Number(dutyPct);
    const normalizedDuty = Number.isFinite(dutyNumber)
      ? Math.max(0, Math.min(100, dutyNumber)) / 100
      : initialDutyPct;
    const sellPriceNum = Number(sellPrice);
    const adNum = Number(adPct);
    const normalizedAd = Number.isFinite(adNum)
      ? Math.max(0, Math.min(100, adNum)) / 100
      : initialAdPct;
    const weightNum = Number(weightKg);
    const updates: Record<string, any> = {
      moq: Number(moq) || initialMoq,
      china_domestic_shipping_krw: chinaKrwPreview,
      customs_duty_pct: normalizedDuty,
      expected_sell_price_krw:
        Number.isFinite(sellPriceNum) && sellPriceNum > 0
          ? Math.round(sellPriceNum)
          : initialSellPrice,
      ad_cost_pct: normalizedAd,
    };
    if (Number.isFinite(weightNum) && weightNum > 0) {
      updates.unit_weight_kg = weightNum;
      updates.shipping_method =
        shippingMethod === 'auto' ? null : shippingMethod;
    } else if (Number.isFinite(Number(intl)) && Number(intl) > 0) {
      // weight 없으면 수동 intl override 유지.
      updates.intl_shipping_krw = Math.max(0, Number(intl));
    }
    await mutation.mutateAsync(updates);
    onSaved();
  };

  return (
    <section className="card">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">
          수입 원가 내역 · 수정
        </h2>
      </header>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">판매가 (KRW)</span>
            <input
              type="number"
              min={0}
              className="input"
              value={sellPrice}
              onChange={(e) => setSellPrice(e.target.value)}
              placeholder={
                naverAvgPrice ? `Naver 평균 ${naverAvgPrice.toLocaleString('ko-KR')}` : '예: 38000'
              }
            />
            <div className="flex flex-wrap gap-1 text-[10px] text-slate-400">
              {naverAvgPrice != null && (
                <button
                  type="button"
                  onClick={() => setSellPrice(String(naverAvgPrice))}
                  className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
                  title="Naver 쇼핑 상위 10개 평균가"
                >
                  Naver 평균 ₩{naverAvgPrice.toLocaleString('ko-KR')}
                </button>
              )}
            </div>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">수입 수량 (MOQ)</span>
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
            <span className="text-xs text-slate-500">
              중국 국내 배송비 (CNY ¥)
            </span>
            <input
              type="number"
              min={0}
              step={0.01}
              className="input"
              value={chinaCny}
              onChange={(e) => setChinaCny(e.target.value)}
              placeholder="예: 20"
            />
            <span className="text-[10px] text-slate-400 tabular-nums">
              ≈ ₩{chinaKrwPreview.toLocaleString('ko-KR')} (환율 {exchangeRateCnyKrw.toFixed(2)})
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">무게 (kg/개)</span>
            <input
              type="number"
              min={0}
              step={0.01}
              className="input"
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
              placeholder="예: 0.5"
            />
            <span className="text-[10px] text-slate-400">
              입력 시 협력사 요율 자동 계산 (국제 배송비 무시)
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">운송방식</span>
            <div className="flex gap-1">
              {[
                { v: 'auto', label: '자동' },
                { v: 'lcl', label: 'LCL' },
                { v: 'sea_self', label: '자가' },
              ].map((opt) => (
                <button
                  key={opt.v}
                  type="button"
                  onClick={() => setShippingMethod(opt.v)}
                  className={
                    shippingMethod === opt.v
                      ? 'flex-1 rounded border border-indigo-400 bg-indigo-50 px-1.5 py-1.5 text-xs font-medium text-indigo-700'
                      : 'flex-1 rounded border border-slate-300 bg-white px-1.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100'
                  }
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <span className="text-[10px] text-slate-400">
              자동: ≤40kg LCL / &gt;40kg 자가
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">국제 배송비 (KRW, 수동)</span>
            <input
              type="number"
              min={0}
              className="input"
              value={intl}
              onChange={(e) => setIntl(e.target.value)}
              placeholder="예: 40000"
              disabled={Number(weightKg) > 0}
            />
            <span className="text-[10px] text-slate-400">
              무게 미입력 시 수동 값 사용
            </span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">관세율 (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step={0.01}
              className="input"
              value={dutyPct}
              onChange={(e) => setDutyPct(e.target.value)}
              placeholder="8.0"
            />
            <div className="flex flex-wrap gap-1 text-[10px] text-slate-400">
              {suggestedBaseDutyPct != null && (
                <button
                  type="button"
                  onClick={() =>
                    setDutyPct((suggestedBaseDutyPct * 100).toFixed(2))
                  }
                  className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
                  title="HS 코드 자동 조회"
                >
                  기본 {(suggestedBaseDutyPct * 100).toFixed(1)}%
                </button>
              )}
              {suggestedKcftaDutyPct != null && (
                <button
                  type="button"
                  onClick={() =>
                    setDutyPct((suggestedKcftaDutyPct * 100).toFixed(2))
                  }
                  className="rounded border border-emerald-300 bg-emerald-50 px-1.5 py-0.5 text-emerald-700 hover:bg-emerald-100"
                  title="한-중 FTA 협정세율 — 5가지 조건 모두 충족 시에만 적용"
                >
                  FTA {(suggestedKcftaDutyPct * 100).toFixed(1)}%
                </button>
              )}
              {suggestedBaseDutyPct == null &&
                suggestedKcftaDutyPct == null && <span>기본 8% (HS 매핑 없음)</span>}
            </div>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-slate-500">광고비 (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step={0.5}
              className="input"
              value={adPct}
              onChange={(e) => setAdPct(e.target.value)}
              placeholder="10"
            />
            <div className="flex flex-wrap gap-1 text-[10px] text-slate-400">
              <button
                type="button"
                onClick={() => setAdPct('0')}
                className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
                title="광고 미집행 (유기적 판매)"
              >
                0%
              </button>
              <button
                type="button"
                onClick={() => setAdPct('5')}
                className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
              >
                5%
              </button>
              <button
                type="button"
                onClick={() => setAdPct('10')}
                className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
              >
                10%
              </button>
              <button
                type="button"
                onClick={() => setAdPct('15')}
                className="rounded border border-slate-300 bg-white px-1.5 py-0.5 hover:bg-slate-100"
              >
                15%
              </button>
            </div>
          </label>
        </div>
        <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <p className="mb-1 font-medium text-slate-700">
            💡 한-중 FTA 적용 = 원산지 증명서 + 4가지 추가 조건
          </p>
          <ol className="list-decimal space-y-0.5 pl-4 text-[11px]">
            <li>
              <strong>원산지 증명서 (C/O)</strong>: 중국 수출자/상공회의소 발급
              (보통 ¥200~500 추가 비용)
            </li>
            <li>
              <strong>원산지 결정 기준 충족</strong>: 세번변경·부가가치·가공공정
              기준 중 하나 (공장 서류 뒷받침)
            </li>
            <li>
              <strong>직접운송</strong>: 중국→한국 직접, 제3국 환적 시 증빙 필요
            </li>
            <li>
              <strong>수입 신고 시 FTA 신청</strong>: 관세사/수입자가 명시 요청
            </li>
            <li>
              <strong>서류 5년 보관</strong>: 사후 검증 시 미제출하면 추징
            </li>
          </ol>
          <p className="mt-2 text-[11px] text-slate-500">
            소량 사입·1688 직구매는 공장이 C/O 발급 비협조인 경우가 많아 실무적으로는
            기본관세로 처리하는 게 현실적입니다. MOQ 크고 공장 직거래면 FTA 추진이 유리.
          </p>
        </div>
        {mutation.error && (
          <p role="alert" className="text-sm text-rose-600">
            {mutation.error instanceof Error
              ? mutation.error.message
              : '저장 실패'}
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={mutation.isPending}
          >
            취소
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? '재계산 중...' : '저장하고 재계산'}
          </button>
        </div>
      </form>
    </section>
  );
}
