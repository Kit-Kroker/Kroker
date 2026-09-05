<script setup lang="ts">
import { profileId } from '../src/profile'
import { REGISTRY } from './registry'
</script>

<template>
  <main class="showcase">
    <section v-for="set in REGISTRY" :key="set.component">
      <h2>{{ set.component }}</h2>
      <article
        v-for="p in set.profiles"
        :key="p.name"
        :id="profileId(set.component, p.name)"
        class="showcase-profile"
      >
        <h3>{{ p.name }}</h3>
        <p>{{ p.summary }}</p>
        <!-- The id is on this wrapper, never on the component root, so
             test infrastructure never constrains a component's markup. -->
        <div class="showcase-stage">
          <component :is="set.target" v-bind="p.props" />
        </div>
      </article>
    </section>
  </main>
</template>
