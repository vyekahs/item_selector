'use client';

import { useState } from 'react';

import { AdminPanel } from '@/components/AdminPanel';
import { KeywordFilterBar } from '@/components/KeywordFilterBar';
import { OpportunityRow } from '@/components/OpportunityRow';
import { useCategories, useOpportunities } from '@/lib/api/queries';

export default function HomePage() {
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [limit, setLimit] = useState<number>(20);
  const [minScore, setMinScore] = useState<number>(0);
  const [includeExcluded, setIncludeExcluded] = useState<boolean>(false);

  const categoriesQuery = useCategories();
  const opportunitiesQuery = useOpportunities({
    category_id: categoryId,
    limit,
    min_score: minScore,
    include_excluded: includeExcluded,
  });

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            🎯 이번주 중국 소싱 기회 TOP {limit}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            한국 시장 수요·성장·경쟁 데이터를 종합해 가장 유망한 키워드를 보여줍니다.
          </p>
        </div>
      </header>

      <AdminPanel />

      <KeywordFilterBar
        categories={categoriesQuery.data?.roots ?? []}
        categoryId={categoryId}
        onCategoryChange={setCategoryId}
        limit={limit}
        onLimitChange={setLimit}
        minScore={minScore}
        onMinScoreChange={setMinScore}
        includeExcluded={includeExcluded}
        onIncludeExcludedChange={setIncludeExcluded}
      />

      {opportunitiesQuery.isLoading ? (
        <p role="status" className="text-sm text-slate-500">
          불러오는 중…
        </p>
      ) : opportunitiesQuery.isError ? (
        <p
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        >
          기회 키워드를 불러오지 못했습니다: {opportunitiesQuery.error.message}
        </p>
      ) : opportunitiesQuery.data && opportunitiesQuery.data.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          조건에 맞는 키워드가 없습니다.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3">
          {(opportunitiesQuery.data ?? []).map((op) => (
            <li key={op.keyword_id}>
              <OpportunityRow opportunity={op} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
