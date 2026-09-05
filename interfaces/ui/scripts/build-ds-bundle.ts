if (process.platform === 'win32' && !process.env.PLAYWRIGHT_BROWSERS_PATH) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = 'D:/own/.pw-browsers'
}

import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { REGISTRY } from '../showcase/registry'
import { profileId } from '../src/profile'
import { preview } from 'vite'

const uiDir = fileURLToPath(new URL('..', import.meta.url))
const OUT = join(uiDir, 'dist-ds')

let server: any = null
let BASE = process.env.SHOWCASE_URL

if (!BASE) {
  try {
    server = await preview({
      root: join(uiDir, 'showcase'),
      preview: { port: 4173 },
    })
    BASE = 'http://localhost:4173'
  } catch {
    BASE = 'http://localhost:4173'
  }
}

const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(BASE)

// One stylesheet for the whole bundle: every profile shares the showcase's
// CSS, so serializing it once per file keeps each preview standalone.
const css: string = await page.evaluate(() =>
  Array.from(document.styleSheets)
    .flatMap((sh) => {
      try {
        return Array.from((sh as CSSStyleSheet).cssRules).map((r) => r.cssText)
      } catch {
        return [] // cross-origin (the Google Fonts sheet); linked below instead
      }
    })
    .join('\n'),
)

for (const set of REGISTRY) {
  for (const p of set.profiles) {
    const html: string = await page
      .locator(`#${profileId(set.component, p.name)} .showcase-stage`)
      .innerHTML()

    // The marker MUST be the literal first line: the Design System pane
    // reads it there, and bundlers strip leading comments, so it is
    // prepended after serialization rather than authored into a template.
    const doc = [
      `<!-- @dsCard group="${set.group}" -->`,
      '<!doctype html>',
      '<meta charset="utf-8">',
      `<title>${set.component} / ${p.name}</title>`,
      '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">',
      `<style>${css}</style>`,
      `<body>${html}</body>`,
    ].join('\n')

    const out = join(OUT, set.component, `${p.name}.html`)
    await mkdir(dirname(out), { recursive: true })
    await writeFile(out, doc, 'utf8')
    console.log(`wrote ${out}`)
  }
}

await browser.close()
if (server) {
  await server.close()
}
