<script setup lang="ts">
import { computed } from 'vue'
import { useUiStore } from '../stores/ui'
import { useFleetStore } from '../stores/fleet'
import type { ProjectMode } from '../api/types'

const ui = useUiStore()
const fleet = useFleetStore()

const isBrown = computed(() => ui.startMode === 'brownfield')
function setMode(m: ProjectMode) {
  ui.startMode = m
}
async function submit() {
  const title = ui.startTitle.trim()
  if (!title) {
    ui.toast('Title required', '#e0b050')
    return
  }
  await fleet.startRun({ title, repo: ui.startRepo, mode: ui.startMode })
  const run = fleet.runs.find((r) => r.title === title)
  ui.toast(run ? `Run started — ${run.id}` : 'Run started', '#5b9dd9')
  ui.resetStartForm()
  ui.closeStart()
}
</script>

<template>
  <div
    v-if="ui.startOpen"
    data-testid="backdrop"
    class="backdrop"
    @click="ui.closeStart()"
  >
    <div data-testid="modal-card" class="card" @click.stop>
      <div class="title">START RUN</div>

      <label class="lbl">FEATURE TITLE</label>
      <input
        v-model="ui.startTitle"
        class="inp"
        placeholder="Add SSO to customer portal"
      />

      <label class="lbl">REPO URL</label>
      <input v-model="ui.startRepo" class="inp mono" placeholder="git@github.com:org/repo" />

      <label class="lbl">MODE</label>
      <div class="modes">
        <button class="mode" :class="{ on: isBrown }" @click="setMode('brownfield')">brownfield</button>
        <button class="mode" :class="{ on: !isBrown }" @click="setMode('greenfield')">greenfield</button>
      </div>

      <div class="actions">
        <button class="ghost" @click="ui.closeStart()">CANCEL</button>
        <button data-testid="submit" class="go" @click="submit">START</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 10, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.card {
  width: 480px;
  background: #10141b;
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 22px 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.title {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: #e8edf5;
  margin-bottom: 18px;
}
.lbl {
  display: block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: #5d6675;
  margin-bottom: 6px;
}
.inp {
  width: 100%;
  background: #0d1016;
  border: 1px solid #2a3140;
  border-radius: 5px;
  color: #d9dfe9;
  font-size: 12.5px;
  padding: 9px 12px;
  margin-bottom: 14px;
  font-family: 'IBM Plex Sans', sans-serif;
}
.mono {
  font-family: 'IBM Plex Mono', monospace;
}
.modes {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.mode {
  cursor: pointer;
  flex: 1;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  padding: 8px 0;
  border-radius: 4px;
  background: #0d1016;
  color: #7d8697;
  border: 1px solid #2a3140;
}
.mode.on {
  background: #2a2310;
  color: #e0b050;
  border-color: #574a2c;
}
.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.ghost {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  padding: 8px 16px;
  background: none;
  color: #8a93a5;
  border: 1px solid #2a3140;
  border-radius: 4px;
}
.ghost:hover {
  color: #d9dfe9;
}
.go {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  font-weight: 600;
  padding: 8px 16px;
  background: #e0b050;
  color: #1a1405;
  border: none;
  border-radius: 4px;
}
.go:hover {
  background: #ecc06a;
}
</style>
