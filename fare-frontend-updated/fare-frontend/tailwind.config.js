export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {
    fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
    boxShadow: {
      panel: '0 10px 40px rgba(15,23,42,.18), 0 2px 8px rgba(15,23,42,.08)',
      sheet: '0 -8px 30px rgba(15,23,42,.16)',
    },
    keyframes: {
      rise: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'none' } },
      pop: { from: { opacity: 0, transform: 'translateY(-6px) scale(.96)' }, to: { opacity: 1, transform: 'none' } },
      fade: { from: { opacity: 0 }, to: { opacity: 1 } },
    },
    animation: { rise: 'rise .25s ease-out both', pop: 'pop .2s ease-out both', fade: 'fade .18s ease-out both' },
  } },
}
