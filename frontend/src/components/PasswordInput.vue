<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import AppIcon from './AppIcon.vue'

defineOptions({ inheritAttrs: false })
const props = defineProps<{ disabled?: boolean; leadingIcon?: string }>()
const model = defineModel<string>({ default: '' })
const visible = ref(false), inputId = useId()
watch(model, value => { if (!value) visible.value = false })
watch(() => props.disabled, disabled => { if (disabled) visible.value = false })
</script>

<template>
  <span class="password-input" :class="{ 'with-leading-icon': leadingIcon }">
    <AppIcon v-if="leadingIcon" class="password-leading-icon" :name="leadingIcon" :size="19" />
    <input v-bind="$attrs" :id="($attrs.id as string) || inputId" v-model="model" :type="visible ? 'text' : 'password'" :disabled="disabled" />
    <button type="button" class="password-toggle" :aria-label="visible ? 'Ocultar contraseña' : 'Mostrar contraseña'"
      :aria-pressed="visible" :aria-controls="($attrs.id as string) || inputId" :disabled="disabled" @click="visible = !visible">
      <AppIcon :name="visible ? 'eye-off' : 'eye'" :size="20" />
    </button>
  </span>
</template>

<style scoped>
.password-input { display: block; position: relative; width: 100%; min-width: 0; }
.password-input input { padding-right: 50px; }
.password-input.with-leading-icon input { padding-left: 46px; }
.password-leading-icon { position: absolute; left: 15px; top: 50%; transform: translateY(-50%); color: #7890a3; pointer-events: none; }
.password-toggle {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  width: 38px; height: 38px; display: grid; place-items: center;
  padding: 0; border: 0; border-radius: 8px; background: transparent; color: #738a9e;
}
.password-toggle:hover { color: var(--teal); background: #eaf5f6; }
.password-toggle:focus-visible { outline: 2px solid var(--teal); outline-offset: 0; }
</style>
