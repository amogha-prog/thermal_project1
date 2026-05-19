/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#0a0e14',
        bg2:     '#111620',
        bg3:     '#161d28',
        panel:   '#1a2130',
        border:  '#1e2d40',
        accent:  '#00d4ff',
        thermal: '#ff4d1a',
        'rgb-c': '#22c55e',
        warn:    '#f59e0b',
        dim:     '#2a3a50',
        muted:   '#4a6080',
      },
      fontFamily: {
        mono: ['"Space Mono"', 'monospace'],
        sans: ['Syne', 'sans-serif'],
      },
      keyframes: {
        fadeIn: { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        flash:  { '0%,100%': { opacity: 0 }, '10%': { opacity: 0.7 }, '40%': { opacity: 0 } },
      },
      animation: {
        fadeIn: 'fadeIn 0.25s ease forwards',
        flash:  'flash 0.4s ease forwards',
      },
    },
  },
  plugins: [],
};
