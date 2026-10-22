<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, messageOf, type User } from '../api'
const props = defineProps<{ user: User; authorizationRequest: string }>()
const emit = defineEmits<{ logout: [] }>()
interface Context { client_name: string; expires_at: number; tenants: { id: string; name: string; mailboxes: { id: string; email: string }[] }[] }
const context = ref<Context | null>(null), selected = ref(''), error = ref(''), busy = ref(false)
async function load() {
  try {
    context.value = await api<Context>('/oauth/context', 'POST', { request: props.authorizationRequest })
    selected.value = context.value.tenants[0]?.id || ''
  } catch (cause) { error.value = messageOf(cause) }
}
async function authorize(approve: boolean) {
  busy.value = true; error.value = ''
  try {
    const result = await api<{ redirect_uri: string }>('/oauth/consent', 'POST', {
      request: props.authorizationRequest, tenant_id: approve ? selected.value : null, approve,
    })
    window.location.assign(result.redirect_uri)
  } catch (cause) { error.value = messageOf(cause); busy.value = false }
}
onMounted(load)
</script>

<template>
  <main class="connection-layout"><section class="card consent-card">
    <a class="brand" href="/"><span class="brand-mark">CM</span> Corporate Mail <b>AI</b></a>
    <span class="eyebrow">AUTORIZACIÓN DE ACCESO</span><h1>Conecta tus correos con ChatGPT</h1>
    <p class="muted">Estás conectado como <strong>{{ user.username || user.email }}</strong>.</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <template v-if="context">
      <p><strong>{{ context.client_name }}</strong> solicita permiso para buscar y leer tus correos autorizados.</p>
      <label v-if="context.tenants.length">Empresa que vas a conectar<select v-model="selected"><option v-for="tenant in context.tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option></select></label>
      <div v-for="tenant in context.tenants.filter(item => item.id === selected)" :key="tenant.id" class="consent-mailboxes"><strong>Buzones disponibles</strong><p v-for="box in tenant.mailboxes" :key="box.id">✓ {{ box.email }}</p></div>
      <p v-if="!context.tenants.length" class="notice">Todavía no tienes buzones activos autorizados. Contacta al administrador.</p>
      <p class="auth-note">El contenido consultado se compartirá con ChatGPT para responderte. Tus correos permanecen en su proveedor. La conexión permite solo lectura.</p>
      <div class="row-actions"><button class="button secondary" :disabled="busy" @click="authorize(false)">Cancelar</button><button class="button primary" :disabled="busy || !selected" @click="authorize(true)">{{ busy ? 'Procesando…' : 'Autorizar conexión' }}</button></div>
    </template>
    <p v-else-if="!error" role="status">Comprobando la solicitud…</p>
    <button class="text-button" @click="emit('logout')">Usar otra cuenta</button>
  </section></main>
</template>
