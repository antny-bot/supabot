import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Pretendard JP Variable', 'Pretendard', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // WDS Blue — primary brand action (replaces indigo). Backed by CSS vars
        // (index.css) so the accent color can be swapped at runtime via
        // html[data-accent="violet|green"].
        primary: {
          50: 'rgb(var(--color-primary-50) / <alpha-value>)',
          100: 'rgb(var(--color-primary-100) / <alpha-value>)',
          200: 'rgb(var(--color-primary-200) / <alpha-value>)',
          300: 'rgb(var(--color-primary-300) / <alpha-value>)',
          400: 'rgb(var(--color-primary-400) / <alpha-value>)',
          500: 'rgb(var(--color-primary-500) / <alpha-value>)',
          600: 'rgb(var(--color-primary-600) / <alpha-value>)',
          700: 'rgb(var(--color-primary-700) / <alpha-value>)',
          800: 'rgb(var(--color-primary-800) / <alpha-value>)',
          900: 'rgb(var(--color-primary-900) / <alpha-value>)',
        },
        // Korean market convention: 수익(상승)=빨강
        up: {
          50: '#feecec',
          100: '#fed5d5',
          400: '#ff6363',
          500: '#e52222',
          600: '#b20c0c',
        },
        // Korean market convention: 손실(하락)=파랑
        down: {
          50: '#eaf2fe',
          100: '#c9defe',
          400: '#4f95ff',
          500: '#1666e0',
          600: '#0054d1',
        },
      },
      borderRadius: {
        // WDS --radius-xl: 16px (card radius)
        xl: '1rem',
      },
      boxShadow: {
        // WDS --shadow-1
        sm: '0 1px 2px 0 rgba(0,0,0,0.04), 0 1px 1px 0 rgba(23,23,23,0.06)',
      },
    },
  },
  plugins: [],
} satisfies Config
