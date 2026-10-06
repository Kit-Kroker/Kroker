<script setup lang="ts">
// 011 T009 (US1, R-6, contract §3): the run's cost breakdown. Dollars reach
// the screen only through shared/cost (the one price rule) — a role with
// tokens and no price reads "not priced", never $0.00; a total mixing priced
// and unpriced rows is labelled partial. The research stage's own spend is
// in neither the trace nor the role list (N5), which is why the note is
// rendered in every state. Plain token-styled markup: no library part can
// carry the not-priced/partial labels without a new variant (plan fallback).
import { computed } from 'vue'
import { useFleetStore } from '../../shared/fleet.store'
import { rowPrice, totalPrice, priceLabel, BUDGET_SCOPE_NOTE } from '../../shared/cost'
import { money, tokens, budgetPct } from '../../shared/format'
import type { RoleCost } from '../../api/types'

const props = defineProps<{ runId: string }>()
const fleet = useFleetStore()

const run = computed(() => fleet.getOrLoad(props.runId))
// Same discipline as the board panel: a store that never fetched is loading;
// a completed fetch without the run has nothing to show either way.
const loading = computed(() => run.value === undefined && fleet.lastFetched === null)
const roles = computed<RoleCost[]>(() => run.value?.roles ?? [])
const total = computed(() => totalPrice(roles.value, run.value?.cost ?? null))
// N9: closed runs written before role tracking carry a total but no rows.
const noBreakdown = computed(
  () => roles.value.length === 0 && total.value.state === 'priced',
)
const budget = computed(() => run.value?.budget ?? null)
const threshold = computed(() => run.value?.budgetThreshold ?? null)
const counted = computed(() => run.value?.budgetCounted ?? null)

function rowTokens(r: RoleCost): string {
  return (
    `in ${tokens(r.inputTokens)} / out ${tokens(r.outputTokens)}` +
    ` / cache read ${tokens(r.cacheReadTokens)} / cache write ${tokens(r.cacheWriteTokens)}`
  )
}
</script>

<template>
  <section data-testid="cost-tab" class="cost">
    <p data-testid="cost-research-note" class="note">
      The research stage has its own search, fetch and cost limits; they are
      separate from the run budget, and its own spend is not listed here.
    </p>

    <p v-if="loading" data-testid="cost-empty" class="empty">Loading…</p>
    <p v-else-if="roles.length === 0 && !noBreakdown" data-testid="cost-empty" class="empty">
      No usage recorded yet.
    </p>
    <div v-else-if="noBreakdown" data-testid="cost-no-breakdown" class="empty">
      <p>No breakdown recorded for this run.</p>
      <p data-testid="cost-total-price" class="total price">{{ priceLabel(total) }}</p>
    </div>

    <table v-else class="rows">
      <thead>
        <tr>
          <th>role</th><th>model</th><th>calls</th><th>tokens</th><th>cost</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in roles" :key="r.role" data-testid="cost-row" :data-role="r.role">
          <td>{{ r.role }}</td>
          <td>{{ r.model }}</td>
          <td>{{ r.calls }}</td>
          <td data-testid="cost-row-tokens">{{ rowTokens(r) }}</td>
          <td data-testid="cost-row-price" class="price">{{ priceLabel(rowPrice(r)) }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td colspan="3">total</td>
          <td data-testid="cost-total-tokens">{{ tokens(total.tokens) }}</td>
          <td data-testid="cost-total-price" class="price">{{ priceLabel(total) }}</td>
        </tr>
      </tfoot>
    </table>

    <div data-testid="cost-budget" class="budget">
      <template v-if="budget === null">
        No budget. Set one when starting a run (--budget-usd or the start form).
      </template>
      <template v-else>
        <span>budget {{ money(budget) }}</span>
        <span v-if="threshold !== null">current limit {{ money(threshold) }}</span>
        <span
          v-if="counted !== null"
          data-testid="cost-budget-counted"
        >counted toward budget {{ money(counted) }}</span>
        <!-- percent = counted over the CURRENT limit, whole percent; a closed
             run keeps no live threshold so it shows no bar (R-3). -->
        <span v-if="threshold !== null" data-testid="cost-budget-pct"
        >{{ Math.floor(budgetPct(counted ?? 0, threshold)) }}%</span>
        <span data-testid="cost-budget-crossings"
        >crossings {{ run?.budgetCrossings ?? 0 }}</span>
        <p data-testid="cost-budget-note">Budget {{ BUDGET_SCOPE_NOTE }}</p>
      </template>
    </div>
  </section>
</template>

<style scoped>
.cost { display: flex; flex-direction: column; gap: 10px; font-family: var(--font-mono); font-size: 12px; color: var(--ink-secondary); }
.note { margin: 0; color: var(--ink-subtle); font-size: 11px; }
.empty { margin: 0; color: var(--ink-subtle); }
.rows { border-collapse: collapse; width: 100%; }
.rows th { text-align: left; color: var(--ink-faint); font-weight: 500; font-size: 11px; padding: 4px 10px 4px 0; border-bottom: 1px solid var(--line); }
.rows td { padding: 4px 10px 4px 0; border-bottom: 1px solid var(--line); }
.rows tfoot td { border-top: 1px solid var(--line); color: var(--ink-primary); font-weight: 600; }
.price { color: var(--ink-primary); }
.budget { display: flex; flex-wrap: wrap; gap: 14px; align-items: baseline; padding-top: 4px; border-top: 1px solid var(--line); }
.budget p { margin: 0; width: 100%; color: var(--ink-subtle); font-size: 11px; }
</style>
