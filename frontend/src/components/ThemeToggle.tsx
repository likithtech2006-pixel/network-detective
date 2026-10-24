import React from 'react';
import { Moon, Sun } from 'lucide-react';
import useTheme from '../hooks/useTheme';

/**
 * Sun/moon button: the icons swap with a turn, and the page re-colors in a growing circle
 */
export const ThemeToggle: React.FC = () => {
  const { theme, setTheme } = useTheme();
  const isLight = theme === 'light';

  const toggle = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTheme(isLight ? 'dark' : 'light', {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
  };

  return (
    <button
      onClick={toggle}
      aria-label={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
      title={isLight ? 'Dark mode' : 'Light mode'}
      className="relative w-9 h-9 flex items-center justify-center rounded-xl border border-gray-800 bg-gray-900 text-gray-300 hover:text-white hover:border-gray-700 transition-colors overflow-hidden"
    >
      <Sun
        className={`absolute w-4 h-4 text-amber-500 transition-all duration-500 ease-out ${
          isLight ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-0 opacity-0'
        }`}
      />
      <Moon
        className={`absolute w-4 h-4 text-indigo-400 transition-all duration-500 ease-out ${
          isLight ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100'
        }`}
      />
    </button>
  );
};

export default ThemeToggle;
