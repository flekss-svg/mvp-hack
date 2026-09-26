import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())

// jsdom не реализует ResizeObserver и Element.scrollTo — их используют компоненты карты,
// шкалы времени и диспетчерской панели. Без заглушек рендер падает с ReferenceError/TypeError.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
Element.prototype.scrollTo ??= () => {}
