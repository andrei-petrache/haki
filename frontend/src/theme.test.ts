import { describe, expect, it } from 'vitest'
// The stylesheet as text, through Vite, as the app ships it
import css from './index.css?raw'

/** The colour tokens of index.css, by name: only plain #rrggbb values. */
function tokens(): Record<string, string> {
  const found: Record<string, string> = {}
  for (const [, name, value] of css.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})\b/gi)) {
    found[name] = value
  }
  return found
}

/** WCAG relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

describe('theme contrast (WCAG AA, 4.5:1 for text)', () => {
  const t = tokens()
  const surfaces = ['ground', 'surface', 'raised', 'nav-bg']

  it.each(['text', 'muted', 'accent-text'])('%s is readable on every surface', (fg) => {
    for (const bg of surfaces) {
      expect(contrast(t[fg], t[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('white text is readable on the accent fill, also when hovered', () => {
    expect(contrast(t['on-accent'], t['accent-fill'])).toBeGreaterThanOrEqual(4.5)
    expect(contrast(t['on-accent'], t['accent-fill-hover'])).toBeGreaterThanOrEqual(4.5)
  })

  it('the focus outline stands out from every surface (3:1, non-text)', () => {
    for (const bg of surfaces) {
      expect(contrast(t.focus, t[bg]), `focus on ${bg}`).toBeGreaterThanOrEqual(3)
    }
  })
})
