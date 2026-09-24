import type { ProfileSet } from '../src/profile'
import stageDots from '../src/components/stage_dots/stage_dots.profiles'
import statusPip from '../src/components/status_pip/status_pip.profiles'
import button from '../src/components/button/button.profiles'
import segmentedControl from '../src/components/segmented_control/segmented_control.profiles'
import surface from '../src/components/surface/surface.profiles'
import tag from '../src/components/tag/tag.profiles'
import filterChip from '../src/components/filter_chip/filter_chip.profiles'
import field from '../src/components/field/field.profiles'
import checkRow from '../src/components/check_row/check_row.profiles'
import fleetRow from '../src/components/fleet_row/fleet_row.profiles'
import fleetTable from '../src/components/fleet_table/fleet_table.profiles'
import appHeader from '../src/components/app_header/app_header.profiles'
import toasts from '../src/components/toasts/toasts.profiles'
import startRunModal from '../src/components/start_run_modal/start_run_modal.profiles'
import gateDecision from '../src/components/gate_decision/gate_decision.profiles'
import nodePalette from '../src/components/node_palette/node_palette.profiles'
import issueList from '../src/components/issue_list/issue_list.profiles'
import yamlPane from '../src/components/yaml_pane/yaml_pane.profiles'
import schemaForm from '../src/components/schema_form/schema_form.profiles'
import graphCanvas from '../src/components/graph_canvas/graph_canvas.profiles'

export const REGISTRY: ProfileSet[] = [
  // primitives first: the showcase reads top-down from foundations to screens
  button,
  segmentedControl,
  surface,
  tag,
  filterChip,
  field,
  stageDots,
  statusPip,
  checkRow,
  fleetRow,
  fleetTable,
  appHeader,
  toasts,
  startRunModal,
  gateDecision,
  nodePalette,
  issueList,
  yamlPane,
  schemaForm,
  graphCanvas,
]
