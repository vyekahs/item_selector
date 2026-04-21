'use client';

import { FormEvent, useState } from 'react';

import { useCreateSeed, useExpandAndRecalculate } from '@/lib/api/mutations';

export function AdminPanel() {
  const [term, setTerm] = useState('');
  const [flash, setFlash] = useState<string | null>(null);
  const createSeed = useCreateSeed();
  const expand = useExpandAndRecalculate();

  const handleAddSeed = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = term.trim();
    if (!trimmed) return;
    try {
      const res = await createSeed.mutateAsync(trimmed);
      setTerm('');
      setFlash(`✅ "${res.term}" → ${res.category_name ?? '기타'} 카테고리로 추가됨`);
    } catch (err) {
      setFlash(
        `❌ 추가 실패: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleExpand = async () => {
    setFlash(null);
    try {
      const res = await expand.mutateAsync();
      setFlash(`🔄 ${res.message}`);
    } catch (err) {
      setFlash(
        `❌ 실행 실패: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  return (
    <section aria-label="관리" className="card flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <form onSubmit={handleAddSeed} className="flex flex-1 items-end gap-2">
          <label className="flex-1">
            <span className="label">시드 키워드 추가</span>
            <input
              className="input"
              placeholder="예: 에어프라이어 (카테고리는 자동 감지)"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              disabled={createSeed.isPending}
            />
          </label>
          <button
            type="submit"
            className="btn-primary"
            disabled={createSeed.isPending || !term.trim()}
          >
            {createSeed.isPending ? '추가 중…' : '➕ 추가'}
          </button>
        </form>
        <button
          type="button"
          onClick={handleExpand}
          className="btn-secondary"
          disabled={expand.isPending}
          title="collect_keywords → metrics → opportunities 파이프라인 실행 (2~3분 소요)"
        >
          {expand.isPending ? '실행 중…' : '🔄 키워드 확장 + 재계산'}
        </button>
      </div>
      {flash && (
        <p
          role="status"
          className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          {flash}
        </p>
      )}
    </section>
  );
}
