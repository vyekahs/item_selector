import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef7ff',
          100: '#d9ecff',
          500: '#2b7fff',
          600: '#1e63d6',
          700: '#1852b0',
        },
        score: {
          excellent: '#16a34a',
          good: '#65a30d',
          ok: '#ca8a04',
          warn: '#ea580c',
          bad: '#dc2626',
        },
      },
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Noto Sans KR',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};

export default config;
