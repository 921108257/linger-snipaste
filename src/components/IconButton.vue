<script setup lang="ts">
import type { Component } from "vue";
withDefaults(
  defineProps<{
    icon: Component;
    label: string;
    active?: boolean;
    disabled?: boolean;
  }>(),
  { active: undefined },
);
</script>
<template>
  <button
    type="button"
    class="icon-button"
    :class="{ active }"
    :aria-label="label"
    :title="label"
    :aria-pressed="active === undefined ? undefined : active"
    :disabled="disabled"
  >
    <component :is="icon" :size="18" :stroke-width="1.7" aria-hidden="true" />
  </button>
</template>
