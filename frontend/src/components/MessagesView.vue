<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, mailboxPath, messageOf, type Mailbox, type MessageDetail, type MessagePage, type MessageSummary, type Tenant } from '../api'
import AppModal from './AppModal.vue'

const props = defineProps<{ tenant: Tenant; mailbox: Mailbox }>()
const emit = defineEmits<{ back: [] }>()
const query = ref(''), unread = ref(false), offset = ref(0), loading = ref(false), opening = ref(false), error = ref('')
const page = ref<MessagePage | null>(null), selected = ref<MessageDetail | null>(null)
const detailOpen = ref(false)
let loadSequence = 0, readSequence = 0
function closeMessage() { detailOpen.value = false; ++readSequence; opening.value = false; selected.value = null; error.value = '' }
async function search(reset = false) {
  if (reset) offset.value = 0
  detailOpen.value = false
  const sequence = ++loadSequence; ++readSequence; selected.value = null; opening.value = false
  loading.value = true; error.value = ''
  try {
    const params = new URLSearchParams({ query: query.value, unread: String(unread.value), limit: '20', offset: String(offset.value) })
    const result = await api<MessagePage>(`${mailboxPath(props.tenant.id, props.mailbox.id)}/messages?${params}`)
    if (sequence === loadSequence) page.value = result
  } catch (cause) { if (sequence === loadSequence) { error.value = messageOf(cause); page.value = null } }
  finally { if (sequence === loadSequence) loading.value = false }
}
async function open(message: MessageSummary) {
  if (!page.value) return
  const sequence = ++readSequence
  detailOpen.value = true; opening.value = true; error.value = ''; selected.value = null
  try {
    const result = await api<MessageDetail>(`${mailboxPath(props.tenant.id, props.mailbox.id)}/messages/${message.uid}?uid_validity=${page.value.uid_validity}`)
    if (sequence === readSequence) selected.value = result
  } catch (cause) { if (sequence === readSequence) error.value = messageOf(cause) }
  finally { if (sequence === readSequence) opening.value = false }
}
function move(direction: number) { offset.value = Math.max(0, offset.value + direction * 20); search() }
onMounted(() => search())
onBeforeUnmount(() => { ++loadSequence; ++readSequence })
</script>

<template>
  <button class="text-button back-button" @click="emit('back')">← Volver a buzones</button>
  <div class="page-heading"><div><span class="eyebrow">BANDEJA DE ENTRADA · SOLO LECTURA</span><h1>{{ mailbox.display_name }}</h1><p class="muted">{{ mailbox.email }}</p></div><span class="pill">INBOX</span></div>
  <form class="card search-bar" @submit.prevent="search(true)"><label class="search-input"><span class="sr-only">Buscar por asunto o remitente</span><input v-model="query" maxlength="200" placeholder="Buscar por asunto o remitente…" /></label><label class="checkbox-label"><input v-model="unread" type="checkbox" /> Solo no leídos</label><button class="button primary" :disabled="loading">{{ loading ? 'Buscando…' : 'Buscar' }}</button></form>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  <div class="inbox-modal-list"><section class="card message-list"><div class="section-heading"><h2>Mensajes</h2><small class="muted">{{ page?.total ?? '—' }} resultados</small></div><div v-if="loading" class="empty-state" role="status">Consultando el servidor de correo…</div><div v-else-if="!page?.items.length" class="empty-state"><h3>No hay mensajes para mostrar</h3><p>Prueba con otra búsqueda o actualiza la bandeja.</p></div><button v-for="message in page?.items || []" v-else :key="message.uid" class="message-item" :class="{ unread: !message.seen, chosen: selected?.uid === message.uid }" :disabled="loading" @click="open(message)"><span class="message-sender">{{ message.sender || 'Remitente desconocido' }}</span><strong>{{ message.subject || '(Sin asunto)' }}</strong><small>{{ message.date }}</small><span v-if="!message.seen" class="unread-dot" aria-label="No leído"></span></button><div v-if="page && !loading" class="pagination"><button class="button secondary small" :disabled="offset === 0" @click="move(-1)">← Anterior</button><small>{{ page.total ? offset + 1 : 0 }}–{{ Math.min(offset + 20, page.total) }} de {{ page.total }}</small><button class="button secondary small" :disabled="offset + 20 >= page.total" @click="move(1)">Siguiente →</button></div></section>
  </div>
  <AppModal :open="detailOpen" :title="selected?.subject || 'Leer mensaje'" description="Vista de solo lectura del correo." size="large" @close="closeMessage">
        <article class="modal-message-detail"><p v-if="error" class="notice error" role="alert">{{ error }}</p><div v-if="opening" class="empty-state" role="status">Abriendo mensaje…</div><template v-else-if="selected"><div class="message-heading"><span class="pill">Vista de solo lectura</span><p><strong>De:</strong> {{ selected.sender }}</p><p><strong>Para:</strong> {{ selected.recipients }}</p><p class="muted">{{ selected.date }}</p></div><p v-if="selected.truncated" class="notice">El texto es extenso y se muestra parcialmente.</p><pre class="message-body">{{ selected.body || '(Este mensaje no contiene texto visible.)' }}</pre><div v-if="selected.attachments.length" class="attachment-list"><strong>Adjuntos del mensaje</strong><span v-for="(filename, index) in selected.attachments" :key="index" class="pill">▧ {{ filename }}</span><small class="muted">Se muestran los nombres; la descarga no está habilitada.</small></div></template><div v-else class="empty-state detail-placeholder"><span class="empty-icon">✉</span><h3>Selecciona un mensaje</h3><p>Su contenido aparecerá aquí sin modificarlo en el servidor.</p></div></article>
    <template #footer><button type="button" class="button secondary" @click="closeMessage">Cerrar mensaje</button></template>
  </AppModal>
</template>
