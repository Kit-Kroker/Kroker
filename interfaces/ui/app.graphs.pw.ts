// The graphs screens (018 T008, split from app.pw.ts; see app.helpers.ts).
// 018 T063 (S15): the CONSOLE-7 test ('the editor renders recorded text and
// holds shape errors with the canvas disabled') is deleted with the YAML
// pane — the clause is tombstoned in app.md; and the CONSOLE-9 test (the
// inspector edit through the YAML paste flow) is deleted per the
// orchestrator ruling — T066 restores it on Design (an edge max_traversals
// edit round-tripping through the parse). The clause reads untested
// mid-phase; SG-5 checks at phase end.
import { test } from '@playwright/test'
import { APP_BASE_URL } from './app.helpers'

test.use({ baseURL: APP_BASE_URL })
