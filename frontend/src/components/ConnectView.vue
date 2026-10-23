<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, messageOf, type User } from '../api'
const props = defineProps<{ user: User; authorizationRequest: string }>()
const emit = defineEmits<{ logout: [] }>()
interface Context { client_name: string; expires_at: number; scope: string; unavailable_mailboxes?: { email: string; status: string }[]; tenants: { id: string; name: string; mailboxes: { id: string; email: string; can_send: boolean }[] }[] }
const context = ref<Context | null>(null), selected = ref(''), error = ref(''), busy = ref(false)
const loading = ref(false)
const allowSending = ref(false)
const tenant = computed(() => context.value?.tenants.find(item => item.id === selected.value))
const sendingRequested = computed(() => context.value?.scope.split(' ').includes('mail:send') || false)
const sendingAllowed = computed(() => sendingRequested.value && !!tenant.value?.mailboxes.some(box => box.can_send))
watch(selected, () => { allowSending.value = false })
async function load() {
  if (props.user.is_platform_admin || loading.value) return
  loading.value = true; error.value = ''; allowSending.value = false
  try {
    context.value = await api<Context>('/oauth/context', 'POST', { request: props.authorizationRequest })
    selected.value = context.value.tenants[0]?.id || ''
  } catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
async function authorize(approve: boolean) {
  busy.value = true; error.value = ''
  try {
    const result = await api<{ redirect_uri: string }>('/oauth/consent', 'POST', {
      request: props.authorizationRequest, tenant_id: approve ? selected.value : null, approve,
      scope: approve && allowSending.value && sendingAllowed.value ? 'mail:read mail:send' : 'mail:read',
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
    <div v-if="user.is_platform_admin" class="notice" role="alert"><strong>Utiliza la cuenta del cliente</strong><p>El administrador configura empresas, buzones y permisos. Para conectar ChatGPT, pulsa «Usar otra cuenta» e ingresa el usuario y la contraseña que asignaste al cliente en Clientes → Configurar acceso.</p></div>
    <template v-else-if="context">
      <p><strong>{{ context.client_name }}</strong> solicita permiso para {{ context.scope.split(' ').includes('mail:send') ? 'buscar, leer y enviar correos desde los buzones que tengan permiso de envío' : 'buscar y leer tus correos autorizados' }}.</p>
      <label v-if="context.tenants.length">Empresa que vas a conectar<select v-model="selected"><option v-for="tenant in context.tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option></select></label>
      <fieldset v-if="selected" class="consent-permissions" :disabled="busy">
        <legend>Elige qué permites a ChatGPT</legend>
        <p>Buscar y leer los correos de tus buzones autorizados.</p>
        <label class="sending-choice"><input v-model="allowSending" type="checkbox" :disabled="!sendingAllowed" />Permitir también enviar y responder correos</label>
        <small v-if="!sendingRequested">Esta conexión de ChatGPT solicitó únicamente lectura. Aunque el administrador habilite envío, esta solicitud no puede ampliarlo. Cancela y crea una nueva conexión con la URL del servidor MCP para solicitar lectura y envío.</small>
        <small v-else-if="!sendingAllowed">El administrador todavía no habilitó el envío para tus buzones. Puedes continuar con solo lectura.</small>
        <small v-else>Es opcional. Si lo dejas desmarcado, esta conexión tendrá solo lectura. Cada envío requiere revisar y confirmar el mensaje.</small>
      </fieldset>
      <div v-if="tenant" class="consent-mailboxes"><strong>Buzones que vas a conectar</strong><p v-for="box in tenant.mailboxes" :key="box.id">✓ {{ box.email }} · {{ box.can_send && allowSending && sendingAllowed ? 'Lectura y envío' : 'Solo lectura' }}</p></div>
      <div v-if="!context.tenants.length" class="notice">
        <template v-if="context.unavailable_mailboxes?.length">
          <strong>Tienes permisos, pero tus buzones todavía no están listos.</strong>
          <p v-for="box in context.unavailable_mailboxes" :key="box.email">{{ box.email }}: {{ box.status === 'disabled' ? 'deshabilitado. El administrador debe habilitarlo y verificar la conexión.' : 'pendiente de verificar la conexión IMAP. El administrador debe abrir Buzones → Verificar.' }}</p>
          <p>Conceder permisos y verificar la conexión son pasos separados. Si el proveedor indica IMAP Port 993, no uses el POP3 Port 995.</p>
        </template>
        <p v-else>Esta cuenta no tiene buzones autorizados en una empresa activa. Solicita al administrador acceso para tu usuario {{ user.username || user.email }} desde Buzones → Permisos.</p>
        <button type="button" class="button secondary" :disabled="busy || loading" @click="load">{{ loading ? 'Actualizando…' : 'Actualizar buzones' }}</button>
      </div>
      <p class="auth-note">El contenido consultado se compartirá con ChatGPT para responderte. Tus correos permanecen en su proveedor. {{ allowSending && sendingAllowed ? 'Autorizas lectura y envío en los buzones habilitados. Revisa el destinatario y el contenido antes de confirmar cada envío.' : 'Estás autorizando solo lectura.' }}</p>
      <div class="row-actions"><button class="button secondary" :disabled="busy || loading" @click="authorize(false)">Cancelar</button><button class="button primary" :disabled="busy || loading || !selected" @click="authorize(true)">{{ busy ? 'Procesando…' : 'Autorizar conexión' }}</button></div>
    </template>
    <p v-else-if="!error" role="status">Comprobando la solicitud…</p>
    <button class="text-button" @click="emit('logout')">Usar otra cuenta</button>
  </section></main>
</template>

<style scoped>
.consent-permissions { margin: 24px 0; padding: 18px; border: 1px solid var(--line); border-radius: 12px; min-width: 0; }
.consent-permissions legend { padding: 0 6px; font-weight: 700; }
.sending-choice { display: flex; flex-direction: row; align-items: flex-start; gap: 10px; margin: 16px 0; }
.sending-choice input { width: 18px; height: 18px; flex: 0 0 18px; margin: 3px 0 0; accent-color: var(--teal); }
.consent-permissions small { display: block; color: var(--muted); line-height: 1.6; }
</style>
