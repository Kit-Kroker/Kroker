import type { ProfileSet } from '../src/profile'
import stageDots from '../src/components/stage_dots/stage_dots.profiles'
import statusPip from '../src/components/status_pip/status_pip.profiles'
import fleetRow from '../src/components/fleet_row/fleet_row.profiles'
import fleetTable from '../src/components/fleet_table/fleet_table.profiles'
import appHeader from '../src/components/app_header/app_header.profiles'
import toasts from '../src/components/toasts/toasts.profiles'
import startRunModal from '../src/components/start_run_modal/start_run_modal.profiles'

export const REGISTRY: ProfileSet[] = [
  stageDots,
  statusPip,
  fleetRow,
  fleetTable,
  appHeader,
  toasts,
  startRunModal,
]
