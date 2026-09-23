// T002 (RED): the by-screen boundary guard (spec 002, R-5,
// contracts/source-layout.md). The scanner below is a deliberate stub --
// every test that reaches it fails until the GREEN task implements it.
// Planted violations live in memory only; the repo never commits one.
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

// Scanner contract (R-5): 'path' entries are absolute file paths, 'root'
// the absolute frontend src root. Every path and resolved specifier is
// normalized to '/' separators before any rule is evaluated (Windows
// path.resolve yields '\'); specifiers are extracted from whole-file text
// (from '...', side-effect import '...', dynamic import('...'),
// vi.mock('...'), import.meta.glob('...')); only relative specifiers are
// resolved; one string is returned per rule violation.
const SPECIFIER_PATTERNS: RegExp[] = [
  /\bfrom\s+['"]([^'"]+)['"]/g,
  /\bimport\s+['"]([^'"]+)['"]/g,
  /\bimport\s*\(\s*['"]([^'"]+)['"]/g,
  /\bvi\.mock\s*\(\s*['"]([^'"]+)['"]/g,
  /\bimport\.meta\.glob\s*\(\s*['"]([^'"]+)['"]/g,
]

const norm = (p: string): string => p.replaceAll('\\', '/').replace(/\/{2,}/g, '/')

// Lexical '.'/'..' resolution that keeps POSIX-leading and drive-letter
// roots intact -- node:path.resolve would inject a drive letter into
// drive-less planted paths on Windows and break every comparison.
function lexicalResolve(p: string): string {
  const out: string[] = []
  for (const part of p.split('/')) {
    if (part === '') {
      if (out.length === 0) out.push('')
    } else if (part === '.') {
      continue
    } else if (part === '..') {
      if (out.length > 1) out.pop()
    } else {
      out.push(part)
    }
  }
  return out.join('/')
}

function relOf(abs: string, root: string): string | null {
  const a = norm(abs)
  const r = norm(root)
  if (a === r) return ''
  return a.startsWith(`${r}/`) ? a.slice(r.length + 1) : null
}

function banned(fromRel: string, toRel: string): boolean {
  const fromLayer = fromRel.split('/')[0]
  const toLayer = toRel.split('/')[0]
  if (fromLayer === 'features') {
    if (toLayer === 'features') {
      return fromRel.split('/')[1] !== toRel.split('/')[1]
    }
    if (toLayer === 'app') {
      return !/^app\/[^/]+\.store\.ts$/.test(toRel)
    }
    return false
  }
  if (fromLayer === 'shared' || fromLayer === 'api') {
    return toLayer === 'features' || toLayer === 'app'
  }
  return false
}

export function violations(
  files: { path: string; text: string }[],
  root: string,
): string[] {
  const found: string[] = []
  for (const file of files) {
    const fileRel = relOf(file.path, root)
    if (!fileRel) continue
    const dir = norm(file.path).slice(0, norm(file.path).lastIndexOf('/'))
    for (const pattern of SPECIFIER_PATTERNS) {
      for (const m of file.text.matchAll(pattern)) {
        const spec = m[1]
        if (!spec.startsWith('.')) continue
        const toRel = relOf(lexicalResolve(`${dir}/${spec}`), root)
        if (toRel !== null && banned(fileRel, toRel)) {
          found.push(`${fileRel} -> ${toRel}`)
        }
      }
    }
  }
  return found
}

function getFiles(dir: string): string[] {
  const entries = readdirSync(dir)
  const files: string[] = []
  for (const e of entries) {
    const full = join(dir, e)
    if (statSync(full).isDirectory()) {
      files.push(...getFiles(full))
    } else if (full.endsWith('.ts') || full.endsWith('.vue')) {
      files.push(full)
    }
  }
  return files
}

const UI_SRC = join(__dirname, '../../../../ui/src')

describe('boundary scanner', () => {
  const ROOT = '/repo/src'
  const plant = (path: string, text: string) => ({ path: `${ROOT}/${path}`, text })

  it('flags a cross-screen import: features/run reaching into features/board', () => {
    const planted = [
      plant('features/run/RunView.vue', "import BoardTab from '../board/BoardTab.vue'"),
    ]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('features/run/RunView.vue')
  })

  it('flags features importing an app module that is not a *.store.ts', () => {
    const planted = [
      plant('features/x/x.ts', "import RunPage from '../../app/RunPage.vue'"),
    ]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('features/x/x.ts')
  })

  it('allows features to import the app shell stores (app/*.store.ts only)', () => {
    const planted = [
      plant('features/x/x.ts', "import { useUiStore } from '../../app/ui.store.ts'"),
    ]
    expect(violations(planted, ROOT)).toEqual([])
  })

  it('flags shared importing from features', () => {
    const planted = [plant('shared/shared.ts', "import { x } from '../features/anything'")]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('shared/shared.ts')
  })

  it('flags api importing from app', () => {
    const planted = [plant('api/api.ts', "import { boot } from '../app/anything.ts'")]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('api/api.ts')
  })

  it('normalizes Windows backslash paths before evaluating rules', () => {
    const planted = [
      {
        path: '\\repo\\src\\features\\run\\RunView.vue',
        text: "import BoardTab from '../board/BoardTab.vue'",
      },
    ]
    const found = violations(planted, '\\repo\\src')
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('features/run/RunView.vue')
  })

  it('extracts specifiers from multi-line imports', () => {
    const planted = [
      plant('shared/format.ts', "import {\n  toStageDots,\n} from '../features/stageStrip.adapter'\n"),
    ]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('shared/format.ts')
  })

  it('follows vi.mock paths as module references', () => {
    const planted = [
      plant('features/run/RunView.test.ts', "vi.mock('../board/BoardTab.vue', () => ({}))"),
    ]
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('features/run/RunView.test.ts')
  })
})

describe('ownership: ui never imports from dashboard', () => {
  it('satisfies the ownership rule: ui never imports from dashboard or api/types', () => {
    function getFiles(dir: string): string[] {
      const entries = readdirSync(dir)
      const files: string[] = []
      for (const e of entries) {
        const full = join(dir, e)
        if (statSync(full).isDirectory()) {
          files.push(...getFiles(full))
        } else if (full.endsWith('.ts') || full.endsWith('.vue')) {
          files.push(full)
        }
      }
      return files
    }

    const uiSrc = join(__dirname, '../../../../ui/src')
    const files = getFiles(uiSrc)
    expect(files.length).toBeGreaterThan(0) // R-5: an empty tree must not pass vacuously

    const violations: string[] = []

    for (const f of files) {
      const content = readFileSync(f, 'utf8')
      if (content.includes("from '../../dashboard") || content.includes('api/types')) {
        violations.push(f)
      }
    }

    expect(violations).toEqual([])
  })
})

describe('ownership: resolver-based', () => {
  it('no relative import in ui/src resolves under interfaces/dashboard/', () => {
    const files = getFiles(UI_SRC)
    expect(files.length).toBeGreaterThan(0)

    // boundaries.test.ts sits at interfaces/dashboard/frontend/src/app/
    const dashboardRoot = resolve(__dirname, '../../..').replaceAll('\\', '/')
    const landing: string[] = []
    for (const f of files) {
      const text = readFileSync(f, 'utf8')
      for (const m of text.matchAll(/from\s+'(\.\.?\/[^']+)'/g)) {
        const resolved = resolve(dirname(f), m[1]).replaceAll('\\', '/')
        if (resolved.startsWith(`${dashboardRoot}/`)) {
          landing.push(`${f}: ${m[1]}`)
        }
      }
    }
    expect(landing).toEqual([])
  })
})

describe('real tree', () => {
  it('app/, features/, shared/ and api/ (whichever exist today) hold no violations', () => {
    const srcRoot = join(__dirname, '..')
    const files: { path: string; text: string }[] = []
    const layerCounts: Record<string, number> = {}
    for (const layer of ['app', 'features', 'shared', 'api']) {
      const dir = join(srcRoot, layer)
      if (!existsSync(dir)) continue // the layer arrives with the task that creates it
      layerCounts[layer] = 0
      for (const f of getFiles(dir)) {
        files.push({ path: f, text: readFileSync(f, 'utf8') })
        layerCounts[layer] += 1
      }
    }
    expect(layerCounts.app ?? 0).toBeGreaterThan(0) // T003: the app shell lives in app/
    expect(violations(files, srcRoot)).toEqual([])
  })
})

// Edge-case companion to 'boundary scanner': specifier forms and path
// shapes the happy cases miss. Same in-memory discipline -- planted files
// never exist on disk, and every case reaches the (still-RED) scanner.
describe('boundary scanner edge cases', () => {
  const ROOT = '/repo/src'
  const plant = (path: string, text: string) => ({ path: `${ROOT}/${path}`, text })
  const flagged = (planted: { path: string; text: string }[], offender: string) => {
    const found = violations(planted, ROOT)
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain(offender)
  }

  it('normalizes Windows drive-letter backslash paths before evaluating rules', () => {
    const planted = [
      {
        path: 'D:\\repo\\src\\features\\run\\RunView.vue',
        text: "import BoardTab from '../board/BoardTab.vue'",
      },
    ]
    const found = violations(planted, 'D:\\repo\\src')
    expect(found.length).toBeGreaterThan(0)
    expect(found.join('\n').replaceAll('\\', '/')).toContain('features/run/RunView.vue')
  })

  it('extracts a specifier landing on a later line of a multi-line import in a .vue file', () => {
    flagged(
      [
        plant(
          'features/run/RunView.vue',
          "<script>\nimport {\n  BoardTab\n} from '../board/BoardTab.vue'\n</script>\n",
        ),
      ],
      'features/run/RunView.vue',
    )
  })

  it('follows vi.mock paths as module references (screen-local api)', () => {
    flagged(
      [plant('features/run/RunView.test.ts', "vi.mock('../board/board.api', () => ({}))")],
      'features/run/RunView.test.ts',
    )
  })

  it('follows dynamic import() specifiers', () => {
    flagged(
      [plant('features/run/RunView.vue', "const store = () => import('../board/board.store')")],
      'features/run/RunView.vue',
    )
  })

  it('follows import.meta.glob specifiers', () => {
    flagged(
      [plant('features/run/RunView.vue', "const tabs = import.meta.glob('../board/*.vue')")],
      'features/run/RunView.vue',
    )
  })

  it('follows side-effect import specifiers', () => {
    flagged([plant('features/run/RunView.vue', "import '../board/thing.css'")], 'features/run/RunView.vue')
  })

  it('resolves ../ chains beyond one hop (deep file reaching another screen)', () => {
    flagged(
      [plant('features/graphs/a/b.vue', "import RunView from '../../run/RunView.vue'")],
      'features/graphs/a/b.vue',
    )
  })

  it('stays clean on legal downward, upward, same-screen and non-relative specifiers', () => {
    const planted = [
      plant('features/fleet/fleet.adapter.ts', "import { format } from '../../shared/format.ts'"),
      plant('features/fleet/FleetView.vue', "import { client } from '../../api/client'"),
      plant('shared/format.ts', "import type { Run } from '../api/types'"),
      plant('app/RunPage.vue', "import FleetView from '../features/fleet/FleetView.vue'"),
      plant(
        'features/fleet/FleetTable.vue',
        "import { computed } from 'vue'\nimport { defineStore } from 'pinia'",
      ),
      plant('features/run/RunView.vue', "import { TabBar } from '@kroker/ui'"),
      // multi-hop resolution landing back in the SAME screen is not a crossing
      plant('features/graphs/a/b.vue', "import View from '../../graphs/GraphEditorView.vue'"),
    ]
    expect(violations(planted, ROOT)).toEqual([])
  })
})

// T003 (RED): the app-shell move (R-6 rows for main.ts, App.vue, router.ts,
// theme.css, shell wrappers, the two shell stores). Every assertion below
// fails until the move lands -- the targets do not exist yet, index.html
// still boots /src/main.ts, and the pre-move files are still in place.
describe('app shell layout (T003)', () => {
  const srcRoot = join(__dirname, '..')

  it('has every app-shell file in its T003 home (R-6 table)', () => {
    const targets = [
      'app/main.ts',
      'app/App.vue',
      'app/App.test.ts',
      'app/router.ts',
      'app/theme.css',
      'app/ui.store.ts',
      'app/inbox.store.ts',
      'app/shell.stores.test.ts',
      'app/shell/AppHeader.vue',
      'app/shell/AppHeader.test.ts',
      'app/shell/StartRunModal.vue',
      'app/shell/StartRunModal.test.ts',
      'app/shell/Toasts.vue',
      'app/shell/Toasts.test.ts',
    ]
    const missing = targets.filter((rel) => !existsSync(join(srcRoot, rel)))
    expect(missing).toEqual([])
  })

  it('boots index.html from /src/app/main.ts', () => {
    const html = readFileSync(join(srcRoot, '..', 'index.html'), 'utf8')
    const entry = html.match(/<script[^>]*\ssrc="([^"]+)"/)
    expect(entry?.[1]).toBe('/src/app/main.ts')
  })

  it('leaves no app-shell source at the pre-move locations', () => {
    expect(existsSync(join(srcRoot, 'stores/ui.ts'))).toBe(false)
    expect(existsSync(join(srcRoot, 'stores/inbox.ts'))).toBe(false)
    expect(existsSync(join(srcRoot, 'styles'))).toBe(false)
  })
})

// T003 (GREEN guard): every relative specifier in the whole dashboard src
// tree -- imports AND vi.mock strings AND dynamic imports AND globs --
// must resolve to a real file on disk. Green today, and it is what keeps
// every later move (T004-T006) honest: a single stale path left behind by
// a git mv shows up here as a miss.
describe('import resolution (T003)', () => {
  it('every relative specifier in the src tree resolves to a file on disk', () => {
    const srcRoot = join(__dirname, '..')

    // Self-exclusion: this file's own text is dense with the scanner
    // self-tests' planted specifiers ('../board/BoardTab.vue' & co.) and
    // the shared regex literals -- those paths do not exist on disk BY
    // DESIGN, so scanning this file would report its fixtures as stale
    // imports. Every other file in the tree is scanned, tests included.
    const SELF = norm(resolve(__dirname, 'boundaries.test.ts'))
    const files = getFiles(srcRoot).filter((f) => norm(f) !== SELF)
    expect(files.length).toBeGreaterThan(0) // an empty walk must not pass vacuously

    const resolvesOnDisk = (native: string): boolean => {
      if (existsSync(native) && statSync(native).isFile()) return true
      for (const suffix of ['.ts', '.tsx', '.vue', '.js']) {
        const p = `${native}${suffix}`
        if (existsSync(p) && statSync(p).isFile()) return true
      }
      const index = join(native, 'index.ts')
      return existsSync(index) && statSync(index).isFile()
    }

    const misses: string[] = []
    for (const f of files) {
      const text = readFileSync(f, 'utf8')
      for (const pattern of SPECIFIER_PATTERNS) {
        for (const m of text.matchAll(pattern)) {
          const spec = m[1]
          if (!spec.startsWith('.')) continue // bare and alias specifiers are not path-resolved
          // import.meta.glob carries wildcards: existence is "the longest
          // wildcard-free prefix names an existing directory" ('../board/*.vue'
          // -> the ../board directory must exist).
          if (spec.includes('*')) {
            const star = spec.indexOf('*')
            const cut = spec.lastIndexOf('/', star)
            const prefix = cut === -1 ? '' : spec.slice(0, cut)
            const base = prefix ? resolve(dirname(f), prefix) : dirname(f)
            if (!(existsSync(base) && statSync(base).isDirectory())) {
              misses.push(`${norm(f)}: ${spec} (glob target directory missing)`)
            }
            continue
          }
          if (!resolvesOnDisk(resolve(dirname(f), spec))) {
            misses.push(`${norm(f)}: ${spec}`)
          }
        }
      }
    }
    expect(misses).toEqual([])
  })
})
