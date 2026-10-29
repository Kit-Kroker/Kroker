// 018 T079 (R-8, read-routes rule 4): the interfaces mock replays the
// recorded fixture (F/api/__fixtures__/read/interfaces.json) through
// the same mapper the http client uses - the mock answers exactly what
// the route serves.
import fixture from '../__fixtures__/read/interfaces.json'
import { mapInterfaces } from '../http-read'
import type { InterfaceMatrix } from '../read-types'

export function mockInterfaces(): InterfaceMatrix {
  return mapInterfaces(fixture as never)
}
