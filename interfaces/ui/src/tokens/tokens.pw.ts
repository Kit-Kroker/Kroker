import { test, expect } from '@playwright/test'

// Asserts that tokens RESOLVE, never what they resolve to. A suite that
// pinned the old palette would burn down in Task 16 (spec C §5).
test('every declared token resolves to a non-empty value', async ({ page }) => {  // clause: TOKENS-1
  await page.goto('/')
  const unresolved = await page.evaluate(() => {
    const s = getComputedStyle(document.documentElement)
    const names = Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule && r.selectorText === ':root')
      .flatMap((r) => Array.from(r.style).filter((p) => p.startsWith('--')))
    return names.filter((n) => s.getPropertyValue(n).trim() === '')
  })
  expect(unresolved).toEqual([])
})

test('no component ships a bare hex literal', async ({ page }) => {  // clause: TOKENS-2
  await page.goto('/')
  const offenders = await page.evaluate(() =>
    Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
      .filter((r) => r.selectorText !== ':root' && /#[0-9a-f]{3,8}\b/i.test(r.style.cssText))
      .map((r) => r.selectorText),
  )
  expect(offenders).toEqual([])
})
