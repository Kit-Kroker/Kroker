import { defineProfiles } from '../../profile'
import YamlPane from './YamlPane.vue'

const TEXT = 'schema_version: 1\nnodes:\n- id: intake\n  type: intake\nedges: []\n'

export default defineProfiles({
  component: 'yaml_pane',
  group: 'Graph',
  target: YamlPane,
  profiles: [
    { name: 'clean', summary: 'Canonical text, nothing to apply.', props: { text: TEXT } },
    {
      name: 'shape-errors',
      summary: 'Text that failed the shape parse, with a YAML error and a model error.',
      props: {
        text: 'schema_version: 1\nnodes: [\n',
        dirty: true,
        errors: [
          { path: '', message: "graph text is not valid YAML: expected the node content, but found '<stream end>'", line: 3, column: 1 },
          { path: 'nodes[0].id', message: "String should match pattern '^[a-z][a-z0-9_]*$'", line: null, column: null },
        ],
      },
    },
    { name: 'dirty', summary: 'Edited text ready to apply.', props: { text: TEXT, dirty: true } },
    { name: 'too-large', summary: 'Text over the byte cap cannot be applied.', props: { text: TEXT, dirty: true, maxBytes: 16 } },
  ],
})
