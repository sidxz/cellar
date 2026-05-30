import "@testing-library/jest-dom";

// Radix UI uses ResizeObserver internally; polyfill for jsdom
if (typeof global.ResizeObserver === "undefined") {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Node 25 ships a built-in `localStorage` (Web Storage API) that intercepts
// `window.localStorage` before jsdom can serve its own implementation, and
// its getter emits a warning + returns an object without `.clear()` when
// `--localstorage-file` is not supplied. Override with a proper in-memory
// store so tests can call `window.localStorage.clear()` as expected.
if (typeof window !== "undefined") {
  const createInMemoryStorage = () => {
    let store: Record<string, string> = {};
    return {
      getItem: (key: string): string | null => store[key] ?? null,
      setItem: (key: string, value: string): void => {
        store[key] = String(value);
      },
      removeItem: (key: string): void => {
        delete store[key];
      },
      clear: (): void => {
        store = {};
      },
      get length(): number {
        return Object.keys(store).length;
      },
      key: (index: number): string | null => Object.keys(store)[index] ?? null,
    };
  };
  Object.defineProperty(window, "localStorage", {
    value: createInMemoryStorage(),
    writable: true,
  });
  Object.defineProperty(window, "sessionStorage", {
    value: createInMemoryStorage(),
    writable: true,
  });
}
