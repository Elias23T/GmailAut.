<script setup lang="ts">
import AppModal from './AppModal.vue'
withDefaults(defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  busy?: boolean
  error?: string
  danger?: boolean
}>(), { confirmLabel: 'Confirmar', busy: false, error: '' })
const emit = defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <AppModal :open="open" :title="title" size="small" :busy="busy" @close="emit('close')">
    <p>{{ message }}</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <template #footer>
      <button type="button" class="button secondary" :disabled="busy" @click="emit('close')">Cancelar</button>
      <button type="button" class="button" :class="danger ? 'danger' : 'primary'" :disabled="busy" @click="emit('confirm')">{{ busy ? 'Procesando…' : confirmLabel }}</button>
    </template>
  </AppModal>
</template>
