import type { Config } from 'tailwindcss'

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      keyframes: {
        typing: {
          '0%, 100%': { transform: 'translateY(0)', opacity: '0.5' },
          '50%':       { transform: 'translateY(-2px)', opacity: '1' },
        },
        'loading-dots': {
          '0%, 100%': { opacity: '0' },
          '50%':       { opacity: '1' },
        },
        wave: {
          '0%, 100%': { transform: 'scaleY(1)' },
          '50%':       { transform: 'scaleY(0.6)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0' },
        },
        'text-blink': {
          '0%, 100%': { color: 'var(--tw-color-primary, white)' },
          '50%':       { color: 'rgba(255,255,255,0.4)' },
        },
        'bounce-dots': {
          '0%, 100%': { transform: 'scale(0.8)', opacity: '0.5' },
          '50%':       { transform: 'scale(1.2)', opacity: '1' },
        },
        'thin-pulse': {
          '0%, 100%': { transform: 'scale(0.95)', opacity: '0.8' },
          '50%':       { transform: 'scale(1.05)', opacity: '0.4' },
        },
        'pulse-dot': {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.8' },
          '50%':       { transform: 'scale(1.5)', opacity: '1' },
        },
        'wave-bars': {
          '0%, 100%': { transform: 'scaleY(1)', opacity: '0.5' },
          '50%':       { transform: 'scaleY(0.6)', opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '200% 50%' },
          '100%': { backgroundPosition: '-200% 50%' },
        },
        'spinner-fade': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'typing':       'typing 1s infinite',
        'loading-dots': 'loading-dots 1.4s infinite',
        'wave':         'wave 1s ease-in-out infinite',
        'blink':        'blink 1s step-end infinite',
        'text-blink':   'text-blink 2s ease-in-out infinite',
        'bounce-dots':  'bounce-dots 1.4s ease-in-out infinite',
        'thin-pulse':   'thin-pulse 1.5s ease-in-out infinite',
        'pulse-dot':    'pulse-dot 1.2s ease-in-out infinite',
        'wave-bars':    'wave-bars 1.2s ease-in-out infinite',
        'shimmer':      'shimmer 4s infinite linear',
        'spinner-fade': 'spinner-fade 1.2s linear infinite',
      },
      backgroundSize: {
        '200': '200% auto',
      },
    },
  },
  plugins: [],
} satisfies Config
