import { useCallback, useEffect, useState } from 'react';
import { flushSync } from 'react-dom';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'nd-theme';
const listeners = new Set<(theme: Theme) => void>();

function readTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the theme still applies for this visit
  }
}

/**
 * Color of a theme variable (e.g. "gray-800") as an rgb() string, for places that
 * cannot use CSS variables such as chart libraries writing SVG attributes.
 */
export function themeColor(name: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--c-${name}`).trim();
  return value ? `rgb(${value.split(' ').join(', ')})` : 'currentColor';
}

/**
 * Light/dark theme. The toggle animates a circle growing from the click point
 * when the browser supports View Transitions, and cross-fades colors otherwise.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readTheme);

  useEffect(() => {
    listeners.add(setThemeState);
    return () => {
      listeners.delete(setThemeState);
    };
  }, []);

  const setTheme = useCallback((next: Theme, origin?: { x: number; y: number }) => {
    const apply = () => {
      document.documentElement.dataset.theme = next;
      saveTheme(next);
      listeners.forEach((listener) => listener(next));
    };

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const doc = document as Document & {
      startViewTransition?: (update: () => void) => { ready: Promise<void> };
    };

    if (reduceMotion) {
      apply();
      return;
    }

    if (!doc.startViewTransition || !origin) {
      const root = document.documentElement;
      root.classList.add('theme-fading');
      apply();
      window.setTimeout(() => root.classList.remove('theme-fading'), 400);
      return;
    }

    const { x, y } = origin;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    const transition = doc.startViewTransition(() => flushSync(apply));
    transition.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        {
          duration: 550,
          easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          pseudoElement: '::view-transition-new(root)',
        }
      );
    });
  }, []);

  return { theme, setTheme };
}

export default useTheme;
