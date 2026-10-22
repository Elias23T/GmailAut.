<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  description?: string
  size?: 'small' | 'medium' | 'large' | 'wide'
  busy?: boolean
}>(), { size: 'medium', busy: false })
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const titleId = useId(), descriptionId = useId()

async function synchronize() {
  await nextTick()
  const element = dialog.value
  if (!element) return
  if (props.open && !element.open) {
    element.showModal()
    const initial = element.querySelector<HTMLElement>(
      '[autofocus], .modal-body input:not([disabled]), .modal-body select:not([disabled])',
    ) || element.querySelector<HTMLElement>('.modal-title')
    initial?.focus({ preventScroll: true })
  } else if (!props.open && element.open) element.close()
}
function close() { if (!props.busy) emit('close') }
function backdrop(event: MouseEvent) {
  const element = dialog.value
  if (!element || event.target !== element) return
  const bounds = element.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close()
}
watch(() => props.open, synchronize)
onMounted(synchronize)
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="app-modal" :class="`modal-${size}`" :aria-labelledby="titleId"
      :aria-describedby="description ? descriptionId : undefined" :aria-busy="busy" :closedby="busy ? 'none' : 'closerequest'"
      @cancel.prevent="close" @keydown.esc.stop.prevent="close" @click="backdrop">
      <template v-if="open">
        <header class="modal-header">
          <div><h2 :id="titleId" class="modal-title" tabindex="-1">{{ title }}</h2><p v-if="description" :id="descriptionId" class="muted">{{ description }}</p></div>
          <button type="button" class="icon-button modal-close" aria-label="Cerrar ventana" :disabled="busy" @click="close">×</button>
        </header>
        <div class="modal-body"><slot /></div>
        <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
      </template>
    </dialog>
  </Teleport>
</template>
