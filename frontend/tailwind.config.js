import defaultColors from 'tailwindcss/colors';
import plugin from 'tailwindcss/plugin';

/**
 * Light and dark themes share every class name. Each color shade is a CSS variable
 * (`--c-<family>-<shade>`, as "R G B") that the light theme redefines, so a class such
 * as `bg-gray-900` is a dark card in the dark theme and a white card in the light one.
 */
const FAMILIES = ['gray', 'red', 'indigo', 'emerald', 'amber', 'blue', 'violet', 'cyan', 'purple', 'sky', 'green'];
const SHADES = ['50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950'];

// Accents in the light theme: dark tints become pale tints and pale text becomes deep text
const ACCENT_LIGHT = {
  50: '900', 100: '900', 200: '800', 300: '700', 400: '600', 500: '500',
  600: '600', 700: '700', 800: '200', 900: '100', 950: '50',
};

// Grays in the light theme run from the page background (950) to ink (50)
const GRAY_LIGHT = {
  950: '#f6f8fb', 900: '#ffffff', 800: '#e2e8f0', 700: '#cbd5e1', 600: '#94a3b8', 500: '#64748b',
  400: '#475569', 300: '#334155', 200: '#1e293b', 100: '#0f172a', 50: '#020617',
};

const rgb = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};

const palette = {};
const darkVars = { '--c-white': '255 255 255' };
const lightVars = { '--c-white': rgb('#0f172a') };

for (const family of FAMILIES) {
  palette[family] = {};
  for (const shade of SHADES) {
    const name = `--c-${family}-${shade}`;
    palette[family][shade] = `rgb(var(${name}) / <alpha-value>)`;
    darkVars[name] = rgb(defaultColors[family][shade]);
    lightVars[name] =
      family === 'gray' ? rgb(GRAY_LIGHT[shade]) : rgb(defaultColors[family][ACCENT_LIGHT[shade]]);
  }
}

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
      black: '#000000',
      white: 'rgb(var(--c-white) / <alpha-value>)',
      // Text on solid accent buttons stays white in both themes
      'on-accent': '#ffffff',
      ...palette,
    },
    extend: {
      colors: {
        network: {
          dark: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          hover: '#273549',
        },
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slideIn 0.3s ease-out forwards',
        'fade-in': 'fadeIn 0.2s ease-out',
        'pop-in': 'popIn 0.22s cubic-bezier(0.2, 0.9, 0.3, 1.2)',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        popIn: {
          '0%': { opacity: '0', transform: 'scale(0.96) translateY(4px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
      },
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      addBase({
        ':root': { ...darkVars, '--shadow-strength': '0.8', 'color-scheme': 'dark' },
        ':root[data-theme="light"]': { ...lightVars, '--shadow-strength': '0.15', 'color-scheme': 'light' },
      });
    }),
  ],
};
