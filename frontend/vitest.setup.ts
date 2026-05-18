import "@testing-library/jest-dom";

// Radix UI uses ResizeObserver internally; polyfill for jsdom
if (typeof global.ResizeObserver === "undefined") {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
