<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, messageOf, type Tenant, type Connection, type ConnectionSettings } from '../api'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
const props = defineProps<{ tenant?: Tenant }>()
const loading = ref(true)
const settings = ref<ConnectionSettings | null>(null), connections = ref<Connection[]>([]), error = ref(''), notice = ref(''), busy = ref(false)
const copied = ref(false), revokeTarget = ref<Connection | null>(null), revokeError = ref('')
async function load() {
  error.value = ''; loading.value = true
  const tenant = props.tenant
  try { [settings.value, connections.value] = await Promise.all([api<ConnectionSettings>('/admin/connection-settings'), tenant ? api<Connection[]>(`/admin/connections?tenant_id=${tenant.id}`) : Promise.resolve([])]) }
  catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
async function copy() {
  try { await navigator.clipboard.writeText(settings.value!.mcp_url); notice.value = 'URL copiada.' }
  catch { notice.value = 'Selecciona la dirección y cópiala manualmente.' }
  copied.value = true
}
async function revoke(connection: Connection) {
  const tenant = props.tenant
  if (busy.value || !tenant) return
  busy.value = true; revokeError.value = ''
  try { await api(`/admin/connections/${connection.membership_id}?tenant_id=${tenant.id}`, 'DELETE'); revokeTarget.value = null; notice.value = 'Conexiones del cliente revocadas. Necesitará autorizar de nuevo.'; await load() }
  catch (cause) { revokeError.value = messageOf(cause) }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <p class="muted">Una dirección para la plataforma. Cada cliente autoriza sus propios buzones.</p>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <section v-if="settings" class="card form-card"><div class="section-heading"><h2>Dirección del servidor MCP</h2><span class="badge" :class="settings.public_https ? 'active' : 'pending'">{{ settings.public_https ? 'HTTPS configurado' : 'Desarrollo local' }}</span></div>
    <div class="copy-url"><input :value="settings.mcp_url" readonly aria-label="URL del servidor MCP" @focus="($event.target as HTMLInputElement).select()" /><button class="button primary" @click="copy">Copiar URL</button></div>
    <p v-if="!settings.public_https" class="notice">Falta configurar un dominio HTTPS para conectar esta dirección desde ChatGPT. El servidor está preparado para las pruebas locales.</p>
    <ol class="connection-steps"><li>Crea el cliente y configura sus buzones.</li><li>Valida la conexión IMAP y autoriza los buzones desde sus permisos.</li><li>El cliente agrega esta URL como servidor MCP personalizado en ChatGPT, si su cuenta lo permite.</li><li>Inicia sesión en nuestra pantalla de validación y autoriza la lectura.</li></ol><p class="muted">{{ settings.authentication }} · Solo búsqueda y lectura de correo.</p>
  </section>
  <section class="card"><div class="section-heading"><h2>{{ tenant ? 'Autorizaciones de ' + tenant.name : 'Autorizaciones de clientes' }}</h2><button class="button secondary small" :disabled="loading || busy" @click="load">Actualizar</button></div><div v-if="loading" class="empty-state" role="status">Cargando conexiones…</div><div v-else-if="!tenant" class="empty-state"><h3>Selecciona una empresa para consultar sus autorizaciones</h3><p>La URL del servidor es compartida. Cada cliente autoriza sus propios buzones después de configurar su empresa.</p></div><div v-else-if="!connections.length" class="empty-state"><h3>Aún no hay conexiones autorizadas</h3><p>Aparecerán aquí cuando un cliente complete la vinculación.</p></div>
    <article v-for="connection in connections" :key="connection.id" class="mailbox-row"><div class="mailbox-info"><strong>{{ connection.name }}</strong><span>{{ connection.email }}</span><small>{{ new Date(connection.created_at).toLocaleString() }}</small></div><span class="badge" :class="connection.active ? 'active' : 'disabled'">{{ connection.active ? 'Autorizado' : 'Inactivo' }}</span><button v-if="connection.active" class="button secondary small" :disabled="busy" @click="revokeTarget = connection; revokeError = ''">Revocar acceso</button></article>
  </section>
  <AppModal :open="copied" title="URL de conexión con ChatGPT" size="small" @close="copied = false">
    <p role="status">{{ notice }}</p>
    <label>Dirección del servidor MCP<input :value="settings?.mcp_url" readonly @focus="($event.target as HTMLInputElement).select()" /></label>
    <template #footer><button type="button" class="button primary" @click="copied = false">Cerrar</button></template>
  </AppModal>
  <ConfirmModal :open="!!revokeTarget" title="Revocar conexión con ChatGPT"
    :message="'Se revocarán las conexiones de ' + (revokeTarget?.name || 'este cliente') + ' en esta empresa. Necesitará autorizar de nuevo el acceso.'"
    confirm-label="Revocar acceso" :busy="busy" :error="revokeError" @close="revokeTarget = null"
    @confirm="revokeTarget && revoke(revokeTarget)" />
</template>
