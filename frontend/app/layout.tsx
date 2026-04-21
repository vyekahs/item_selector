import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import Link from 'next/link';

import './globals.css';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'itemSelector — 중국 소싱 기회 발굴',
  description:
    '한국 시장 키워드 기반으로 1688 소싱 기회를 발굴하고 스마트스토어·쿠팡 2채널 수익을 비교합니다.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
            <nav
              aria-label="Primary"
              className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3"
            >
              <Link
                href="/"
                className="text-base font-semibold text-slate-900 hover:text-brand-600"
              >
                itemSelector
              </Link>
              <ul className="flex items-center gap-2 text-sm">
                <li>
                  <Link
                    href="/"
                    className="rounded px-3 py-1.5 text-slate-700 hover:bg-slate-100"
                  >
                    기회 키워드
                  </Link>
                </li>
                <li>
                  <Link
                    href="/history"
                    className="rounded px-3 py-1.5 text-slate-700 hover:bg-slate-100"
                  >
                    이력
                  </Link>
                </li>
              </ul>
            </nav>
          </header>
          <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
