/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#020617', // Very deep slate
        bg2:     '#0B1120', // Midnight blueish
        bg3:     '#0f172a',
        panel:   'rgba(15, 23, 42, 0.65)', // Glassy panel
        border:  '#1e293b',
        accent:  '#00e5ff', // Cyber cyan
        thermal: '#ff3a00', // Deep thermal orange
        'rgb-c': '#10b981',
        warn:    '#f59e0b',
        dim:     '#1e293b',
        muted:   '#64748b',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'monospace'],
        sans: ['Outfit', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        'glow': '0 0 15px rgba(0, 229, 255, 0.3)',
        'glow-thermal': '0 0 15px rgba(255, 58, 0, 0.3)',
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
