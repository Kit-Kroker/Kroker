import { test, expect } from '@playwright/test'

const THEME_SCOPES = [':root', '[data-theme="light"]']
const INVARIANT = /^--(font|text|space|radius)-/
const ALIAS = /^var\(--/

// Asserts that tokens RESOLVE, never what they resolve to.
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
  const offenders = await page.evaluate((scopes) =>
    Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
      .filter((r) => !scopes.includes(r.selectorText) && /#[0-9a-f]{3,8}\b/i.test(r.style.cssText))
      .map((r) => r.selectorText),
  THEME_SCOPES)
  expect(offenders).toEqual([])
})

test('light theme redeclares every themed token', async ({ page }) => {  // clause: TOKENS-3
  await page.goto('/')
  const decl = await page.evaluate((scopes) => {
    const rules = Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
    const of = (sel: string) => rules.filter((r) => r.selectorText === sel)
      .flatMap((r) => Array.from(r.style).filter((p) => p.startsWith('--')).map((p) => [p, r.style.getPropertyValue(p).trim()]))
    return { dark: of(scopes[0]), light: of(scopes[1]).map(([p]) => p) }
  }, THEME_SCOPES)
  const themed = decl.dark.filter(([p, v]) => !INVARIANT.test(p) && !ALIAS.test(v)).map(([p]) => p)
  expect(themed.filter((p) => !decl.light.includes(p))).toEqual([])
})

test('deprecated names are aliases only', async ({ page }) => {  // clause: TOKENS-4
  await page.goto('/')
  const raw = await page.evaluate(() => {
    const legacy = /^--(ground-[0-5]|line-faint|ink-(tertiary|identifier|faint|subtle|whisper)|accent.*|link|status-(blocked|quarantined|pending|skipped))$/
    return Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
      .flatMap((r) => Array.from(r.style).filter((p) => legacy.test(p)).map((p) => r.style.getPropertyValue(p).trim()))
      .filter((v) => !v.startsWith('var(--'))
  })
  expect(raw).toEqual([])
})
