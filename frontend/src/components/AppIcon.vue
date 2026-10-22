<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string[]> = {
  layout: ['M3 4h18v16H3z', 'M9 4v16'],
  mail: ['M3 5h18v14H3z', 'm3 6 9 7 9-7'],
  inbox: ['M4 4h16l2 11v5H2v-5L4 4Z', 'M2 15h6l2 3h4l2-3h6'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M16 3a4 4 0 0 1 0 8', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0'],
  user: ['M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2', 'M16 5a4 4 0 1 1-8 0 4 4 0 0 1 8 0'],
  lock: ['M6 10h12v11H6z', 'M8 10V6a4 4 0 0 1 8 0v4', 'M12 15v2'],
  eye: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z', 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0'],
  'eye-off': ['M3 3l18 18', 'M10.5 5.1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.2 4', 'M6.1 6.1A21 21 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.9-1.9', 'M10 10a3 3 0 0 0 4 4'],
  building: ['M4 21V3h12v18', 'M16 9h4v12H2', 'M8 7h4M8 11h4M8 15h4M8 21v-2h4v2'],
  link: ['M10 13a5 5 0 0 0 7 .5l3-3a5 5 0 0 0-7-7l-2 2', 'M14 11a5 5 0 0 0-7-.5l-3 3a5 5 0 0 0 7 7l2-2'],
  activity: ['M3 3v18h18', 'm6 15 4-4 4 2 6-7'],
  shield: ['m12 3 8 4v5c0 5-8 9-8 9s-8-4-8-9V7l8-4Z', 'm8 12 3 3 5-6'],
  help: ['M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3', 'M12 17h.01', 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0'],
  chevron: ['m9 5 7 7-7 7'],
  down: ['m6 9 6 6 6-6'],
  plus: ['M12 5v14M5 12h14'],
  search: ['M21 21l-4.5-4.5', 'M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0'],
  refresh: ['M20 7v5h-5', 'M4 17v-5h5', 'M6 7a7 7 0 0 1 11.5-1L20 9M4 15l2.5 3A7 7 0 0 0 18 17'],
  logout: ['M9 4H4v16h5', 'M9 12h12m-4-4 4 4-4 4'],
  check: ['m5 12 4 4L19 6'],
  warning: ['m12 3 10 18H2L12 3Z', 'M12 9v4M12 17h.01'],
  clock: ['M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', 'M12 6v6l4 2'],
  home: ['m3 10 9-7 9 7', 'M5 9v12h14V9', 'M9 21v-8h6v8'],
  x: ['m6 6 12 12M6 18 18 6'],
  arrow: ['M4 12h16m-6-6 6 6-6 6'],
}
</script>

<template>
  <svg class="app-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path v-for="(path, index) in paths[name] || paths.mail" :key="index" :d="path" />
  </svg>
</template>
