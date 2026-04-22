'use client';

import { useState } from 'react';

import { useSeedCandidates } from '@/lib/api/queries';
import {
  useApproveCandidates,
  useDiscoverSeeds,
} from '@/lib/api/mutations';
import { formatCompact, formatKrw } from '@/lib/utils/format';

export function SeedCandidatesPanel() {
  const candidatesQuery = useSeedCandidates(30);
  const discover = useDiscoverSeeds();
  const approve = useApproveCandidates();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);

  const toggle = (id: number) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDiscover = async () => {
    setFlash(null);
    try {
      const res = await discover.mutateAsync();
      setFlash(`🔍 ${res.message}`);
    } catch (err) {
      setFlash(
        `❌ 실행 실패: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleApprove = async () => {
    if (selected.size === 0) return;
    setFlash(null);
    try {
      const res = await approve.mutateAsync([...selected]);
      setSelected(new Set());
      setFlash(
        `✅ ${res.promoted}개 시드로 승격됨. "🔄 키워드 확장 + 재계산" 눌러서 점수 채우세요.`,
      );
    } catch (err) {
      setFlash(
        `❌ 승인 실패: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const candidates = candidatesQuery.data ?? [];

  return (
    <section aria-label="시드 후보" className="card flex flex-col gap-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            🔍 추천 시드 후보
          </h2>
          <p className="text-xs text-slate-500">
            관세청 수입 급증 상품 + Naver 검색량 결합 자동 발굴
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleDiscover}
            disabled={discover.isPending}
            className="btn-secondary"
            title="5~30분 백그라운드 실행"
          >
            {discover.isPending ? '실행 중…' : '🔎 후보 새로 발굴'}
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={selected.size === 0 || approve.isPending}
            className="btn-primary"
          >
            {approve.isPending
              ? '승격 중…'
              : `✅ 선택 ${selected.size}개 시드로 추가`}
          </button>
        </div>
      </header>

      {flash && (
        <p
          role="status"
          className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          {flash}
        </p>
      )}

      {candidatesQuery.isLoading ? (
        <p className="text-sm text-slate-500">불러오는 중…</p>
      ) : candidates.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500">
          아직 후보가 없습니다. "🔎 후보 새로 발굴" 눌러서 시작하세요.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 w-8"></th>
                <th className="py-2">키워드</th>
                <th className="py-2">점수</th>
                <th className="py-2">월 검색</th>
                <th className="py-2">수입 3M</th>
                <th className="py-2">수입 성장</th>
                <th className="py-2">평균 단가</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-slate-100 text-slate-700"
                >
                  <td className="py-1.5">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => toggle(c.id)}
                    />
                  </td>
                  <td className="py-1.5 font-medium text-slate-900">
                    {c.term}
                  </td>
                  <td className="py-1.5 tabular-nums">
                    {c.combined_score.toFixed(0)}
                  </td>
                  <td className="py-1.5 tabular-nums">
                    {formatCompact(c.monthly_search_volume)}
                  </td>
                  <td className="py-1.5 tabular-nums">
                    {formatKrw(c.import_value_krw_3m)}
                  </td>
                  <td className="py-1.5 tabular-nums text-emerald-700">
                    {c.import_growth_3m_pct != null
                      ? `+${c.import_growth_3m_pct.toFixed(0)}%`
                      : '—'}
                  </td>
                  <td className="py-1.5 tabular-nums">
                    {formatKrw(c.avg_unit_price_krw)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
