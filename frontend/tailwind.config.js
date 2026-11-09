/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f9fafb',
        ink: '#111827',
        muted: '#6b7280',
        line: '#e5e7eb',
        brand: {
          DEFAULT: '#2563eb',
          dark: '#1d4ed8',
          soft: '#eef4ff',
        },
        navy: {
          DEFAULT: '#0a1428',
          soft: '#111f38',
          line: '#1e2d49',
        },
        violet: {
          DEFAULT: '#7c5cff',
          soft: '#f2efff',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)',
        pop: '0 16px 40px rgba(16, 24, 40, 0.14)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};
