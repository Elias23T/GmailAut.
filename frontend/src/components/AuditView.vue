<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, messageOf, tenantPath, type AuditEvent, type Tenant } from '../api'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ tenant: Tenant }>()
const events = ref<AuditEvent[]>([]), loading = ref(true), error = ref(''), offset = ref(0)
const actions: Record<string, string> = { 'tenant.create': 'Empresa creada', 'tenant.update': 'Empresa actualizada', 'membership.add': 'Miembro incorporado', 'membership.update': 'Miembro actualizado', 'mailbox.create': 'Buzón conectado', 'mailbox.update': 'Buzón actualizado', 'mailbox.check': 'Conexión verificada', 'mailbox.grant': 'Lectura autorizada', 'mailbox.revoke': 'Autorización revocada', 'mail.search': 'Búsqueda de correos', 'mail.read': 'Lectura de mensaje', 'authorization.tenant': 'Acceso a empresa', 'authorization.mailbox': 'Acceso a buzón', 'authorization.admin': 'Operación administrativa' }
async function load(direction = 0) {
  offset.value = Math.max(0, offset.value + direction * 50); loading.value = true; error.value = ''
  try { events.value = await api<AuditEvent[]>(`${tenantPath(props.tenant.id)}/audit?limit=50&offset=${offset.value}`) }
  catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
onMounted(() => load())
</script>

<template>
  <div class="page-heading"><div><h1>Actividad de tu empresa</h1><p class="muted">Un historial de operaciones que no almacena contenido de los correos.</p></div><button class="button secondary" :disabled="loading" @click="load()"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
  <p v-if="error" role="alert" class="notice error">{{ error }}</p>
  <section class="card"><div v-if="loading" class="empty-state" role="status">Cargando actividad…</div><div v-else-if="!events.length" class="empty-state"><h3>No hay más eventos</h3><p>Las operaciones de esta empresa aparecerán aquí.</p></div><div v-else class="table-scroll"><table><thead><tr><th>Operación</th><th>Resultado</th><th>Fecha</th><th>Referencia</th></tr></thead><tbody><tr v-for="event in events" :key="event.id"><td><strong>{{ actions[event.action] || event.action }}</strong><small class="block muted">Usuario {{ event.actor_user_id?.slice(0, 8) || 'Sistema' }}</small></td><td><span class="badge" :class="event.outcome">{{ event.outcome === 'success' ? 'Completado' : event.outcome === 'denied' ? 'Denegado' : 'Error' }}</span></td><td>{{ new Date(event.created_at).toLocaleString('es-BO') }}</td><td><code :title="event.request_id">{{ event.request_id.slice(0, 8) }}</code></td></tr></tbody></table></div><div class="pagination"><button class="button secondary small" :disabled="loading || !offset" @click="load(-1)">← Anterior</button><small>Página {{ offset / 50 + 1 }}</small><button class="button secondary small" :disabled="loading || events.length < 50" @click="load(1)">Siguiente →</button></div></section>
</template>
