<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, mailboxPath, messageOf, statusName, tenantPath, type Grant, type Mailbox, type Client, type Tenant } from '../api'
import MessagesView from './MessagesView.vue'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import AppIcon from './AppIcon.vue'
import PasswordInput from './PasswordInput.vue'

const props = defineProps<{ tenant: Tenant }>()
const canManage = true
const mailboxes = ref<Mailbox[]>([]), loading = ref(true), busy = ref(false), error = ref(''), notice = ref('')
const showForm = ref(false), editing = ref<Mailbox | null>(null), reading = ref<Mailbox | null>(null), permissions = ref<Mailbox | null>(null)
const checking = ref<Mailbox | null>(null), statusTarget = ref<Mailbox | null>(null)
const checkingSmtp = ref(false)
const formError = ref(''), permissionsError = ref(''), checkError = ref(''), statusError = ref('')
const members = ref<Client[]>([]), grants = ref<Grant[]>([]), grantsBusy = ref(false)
const form = reactive({ webmail_url: '', email: '', display_name: '', imap_host: '', imap_port: 993, username: '', password: '', smtp_enabled: false, smtp_host: '', smtp_port: 465, smtp_security: 'tls' as 'tls' | 'starttls' })
const isGmail = computed(() => form.imap_host.trim().toLowerCase() === 'imap.gmail.com'
  || /@(gmail|googlemail)\.com$/i.test(form.email.trim()))
watch(() => form.username, (username, previous) => {
  if (!editing.value && (!form.email || form.email === previous)) {
    form.email = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username) ? username : ''
  }
})
const activeCount = computed(() => mailboxes.value.filter(mailbox => mailbox.status === 'active').length)
const query = ref(''), stateFilter = ref('')
const filteredMailboxes = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('es')
  return mailboxes.value.filter(mailbox => (!stateFilter.value || mailbox.status === stateFilter.value)
    && (!term || (mailbox.display_name + ' ' + mailbox.email).toLocaleLowerCase('es').includes(term)))
})
const myCount = computed(() => mailboxes.value.filter(mailbox => mailbox.can_read).length)

async function load() {
  loading.value = true; error.value = ''
  try { mailboxes.value = await api<Mailbox[]>(tenantPath(props.tenant.id) + '/mailboxes') }
  catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
function openForm(mailbox: Mailbox | null = null) {
  editing.value = mailbox; formError.value = ''; notice.value = ''
  form.webmail_url = mailbox?.webmail_url || ''
  Object.assign(form, mailbox ? { email: mailbox.email, display_name: mailbox.display_name, imap_host: mailbox.imap_host, imap_port: mailbox.imap_port, username: '', password: '' }
    : { email: '', display_name: '', imap_host: '', imap_port: 993, username: '', password: '' })
  Object.assign(form, { smtp_enabled: mailbox?.smtp_enabled || false, smtp_host: mailbox?.smtp_host || '', smtp_port: mailbox?.smtp_port || 465, smtp_security: mailbox?.smtp_security || 'tls' })
  showForm.value = true
}
function closeForm() { showForm.value = false; form.password = ''; formError.value = '' }
async function save() {
  if (busy.value) return
  if (!editing.value && !form.email.trim()) {
    formError.value = 'Falta el correo del buzón. Pega tu correo en Username o completa Correo del buzón si tu proveedor utiliza otro usuario.'
    return
  }
  busy.value = true; formError.value = ''; notice.value = ''
  try {
    const body = { webmail_url: form.webmail_url.trim() || null, display_name: form.display_name.trim() || form.email.slice(0, 120), imap_host: form.imap_host, imap_port: form.imap_port,
      smtp_enabled: form.smtp_enabled, ...(form.smtp_host ? { smtp_host: form.smtp_host } : {}), smtp_port: form.smtp_port, smtp_security: form.smtp_security,
      ...(form.username ? { username: form.username } : {}), ...(form.password ? { password: form.password } : {}),
      ...(!editing.value ? { email: form.email, username: form.username || form.email, password: form.password } : {}),
    }
    await api(editing.value ? mailboxPath(props.tenant.id, editing.value.id) : tenantPath(props.tenant.id) + '/mailboxes', editing.value ? 'PATCH' : 'POST', body)
    closeForm(); notice.value = 'Buzón guardado.'; await load()
  } catch (cause) { formError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function check(mailbox: Mailbox, smtp = false) {
  if (busy.value) return
  checking.value = mailbox; checkingSmtp.value = smtp; busy.value = true; checkError.value = ''; notice.value = ''
  try {
    await api(mailboxPath(props.tenant.id, mailbox.id) + (smtp ? '/smtp-check' : '/check'), 'POST')
    notice.value = smtp ? 'SMTP verificado. Esta comprobación no envía correos.' : 'Conexión verificada. El buzón está listo para lectura.'; await load()
  } catch (cause) { checkError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function changeStatus(mailbox: Mailbox) {
  if (busy.value) return
  busy.value = true; statusError.value = ''
  try {
    await api(mailboxPath(props.tenant.id, mailbox.id), 'PATCH', { status: mailbox.status === 'disabled' ? 'pending' : 'disabled' })
    statusTarget.value = null; await load()
  } catch (cause) { statusError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function openPermissions(mailbox: Mailbox) {
  permissions.value = mailbox; grantsBusy.value = true; permissionsError.value = ''; members.value = []; grants.value = []
  try {
    [members.value, grants.value] = await Promise.all([
      api<Client[]>('/admin/clients?tenant_id=' + props.tenant.id), api<Grant[]>(mailboxPath(props.tenant.id, mailbox.id) + '/grants'),
    ])
  } catch (cause) { permissionsError.value = messageOf(cause) }
  finally { grantsBusy.value = false }
}
function hasAccess(member: Client) { return grants.value.some(grant => grant.membership_id === member.membership_id) }
function canSend(member: Client) { return grants.value.some(grant => grant.membership_id === member.membership_id && grant.can_send) }
async function toggleSending(membershipId: string) {
  if (!permissions.value || grantsBusy.value) return
  grantsBusy.value = true; permissionsError.value = ''
  try {
    const updated = await api<Grant>(mailboxPath(props.tenant.id, permissions.value.id) + '/grants/' + membershipId, 'PATCH', { can_send: !grants.value.some(grant => grant.membership_id === membershipId && grant.can_send) })
    grants.value = grants.value.map(grant => grant.membership_id === membershipId ? updated : grant)
    await load()
  } catch (cause) { permissionsError.value = messageOf(cause) }
  finally { grantsBusy.value = false }
}
async function toggleAccess(member: Client) {
  if (!permissions.value || grantsBusy.value) return
  grantsBusy.value = true; permissionsError.value = ''
  const path = mailboxPath(props.tenant.id, permissions.value.id) + '/grants'
  try {
    if (hasAccess(member)) { await api(path + '/' + member.membership_id, 'DELETE'); grants.value = grants.value.filter(grant => grant.membership_id !== member.membership_id) }
    else { grants.value.push(await api<Grant>(path, 'POST', { membership_id: member.membership_id })) }
    await load()
  } catch (cause) { permissionsError.value = messageOf(cause) }
  finally { grantsBusy.value = false }
}
onMounted(load)
</script>

<template>
  <AppModal :open="!!reading" :title="reading?.display_name || 'Bandeja de entrada'" :description="reading?.email" size="wide" @close="reading = null">
    <MessagesView v-if="reading" :key="reading.id" :tenant="tenant" :mailbox="reading" @back="reading = null" />
  </AppModal>
  <div>
    <div class="page-heading"><div><h1>Buzones corporativos</h1><p class="muted">Conecta tus cuentas de correo y administra quién puede consultarlas.</p></div><button v-if="canManage" type="button" class="button primary" @click="openForm()"><AppIcon name="plus" :size="18" />Conectar buzón</button></div>
    <div class="stats-grid"><div class="stat-card"><span>Buzones<AppIcon name="mail" :size="19" /></span><strong>{{ mailboxes.length }}</strong><small>En {{ tenant.name }}</small></div><div class="stat-card"><span>Conexiones activas<AppIcon name="check" :size="19" /></span><strong class="metric-success">{{ activeCount }}</strong><small>Listas para consultar</small></div><div class="stat-card"><span>Mis autorizaciones<AppIcon name="shield" :size="19" /></span><strong>{{ myCount }}</strong><small>Accesos de solo lectura</small></div></div>
    <p v-if="error" role="alert" class="notice error">{{ error }}</p><p v-if="notice" role="status" class="notice success">{{ notice }}</p>
    <AppModal :open="showForm" :title="editing ? 'Configurar buzón' : 'Conectar un buzón'" size="large" :busy="busy" @close="closeForm">
      <p v-if="formError" class="notice error" role="alert">{{ formError }}</p>
      <form id="mailbox-form" @submit.prevent="save">
        <label for="mailbox-url">URL: (opcional)
          <input id="mailbox-url" v-model.trim="form.webmail_url" type="url" pattern="https://.*" maxlength="2048" placeholder="https://webmail.empresa.com:2096/" :disabled="busy" />
        </label>
        <div class="form-grid">
          <label for="mailbox-username">Username:
            <input id="mailbox-username" v-model.trim="form.username" :required="!editing" maxlength="320" autocomplete="off" :placeholder="editing ? 'Vacío para conservar el usuario guardado' : 'cuenta@empresa.com'" :disabled="busy" />
          </label>
          <div class="mailbox-password-field">
            <label for="mailbox-password">Password:
              <PasswordInput id="mailbox-password" v-model="form.password" :required="!editing" maxlength="1024" :disabled="busy" :placeholder="editing ? 'Dejar vacío para conservar la clave guardada' : isGmail ? 'Pega la clave generada por Google' : 'Escribe la contraseña actual de este correo'" autocomplete="new-password" />
            </label>
          </div>
          <label for="mailbox-incoming">Incoming Server:
            <input id="mailbox-incoming" v-model.trim="form.imap_host" required maxlength="253" placeholder="mail.empresa.com" :disabled="busy" />
          </label>
          <label for="mailbox-imap-port">IMAP Port:
            <input id="mailbox-imap-port" v-model.number="form.imap_port" type="number" required min="1" max="65535" :disabled="busy" />
          </label>
        </div>
        <label class="checkbox-label"><input v-model="form.smtp_enabled" type="checkbox" :disabled="busy" />Habilitar envío de correos desde este buzón</label>
        <div class="form-grid">
          <label for="mailbox-outgoing">Outgoing Server:
            <input id="mailbox-outgoing" v-model.trim="form.smtp_host" :required="form.smtp_enabled" maxlength="253" placeholder="mail.empresa.com" :disabled="busy" />
          </label>
          <label for="mailbox-smtp-port">SMTP Port:
            <input id="mailbox-smtp-port" v-model.number="form.smtp_port" type="number" required min="1" max="65535" :disabled="busy" />
          </label>
          <label for="mailbox-smtp-security">Seguridad SMTP:
            <select id="mailbox-smtp-security" v-model="form.smtp_security" :disabled="busy" @change="form.smtp_port = form.smtp_security === 'tls' ? 465 : 587"><option value="tls">TLS directo · Habitualmente 465</option><option value="starttls">STARTTLS · Habitualmente 587</option></select>
          </label>
          <label for="mailbox-email">Correo del buzón:
            <input id="mailbox-email" v-model.trim="form.email" type="email" required maxlength="320" :readonly="!!editing" :disabled="busy" placeholder="cuenta@empresa.com" />
          </label>
          <label for="mailbox-name">Nombre visible: (opcional)<input id="mailbox-name" v-model="form.display_name" maxlength="120" :placeholder="form.email || 'Se utilizará el correo del buzón'" :disabled="busy" /></label>
        </div>
      </form>
      <template #footer><button type="button" class="button secondary" :disabled="busy" @click="closeForm">Cancelar</button><button form="mailbox-form" type="submit" class="button primary" :disabled="busy">{{ busy ? 'Guardando…' : 'Guardar buzón' }}</button></template>
    </AppModal>
    <AppModal :open="!!permissions" :title="'Acceso a ' + (permissions?.display_name || 'buzón')" description="Autoriza lectura y, por separado, el envío desde este buzón." size="large" :busy="grantsBusy" @close="permissions = null">
      <p v-if="permissionsError" class="notice error" role="alert">{{ permissionsError }}</p>
      <p v-if="!grantsBusy && !members.length && !permissionsError" class="notice">Agrega un cliente desde la sección Clientes para concederle acceso.</p>
      <p v-if="!permissions?.smtp_enabled" class="notice">Para conceder envío, habilita primero SMTP desde Editar buzón.</p>
      <p v-if="permissions && permissions.status !== 'active'" class="notice" role="status">Los permisos se guardan, pero este buzón {{ permissions.status === 'disabled' ? 'está deshabilitado. Habilítalo y verifica la conexión' : 'todavía no tiene una conexión IMAP verificada. Cierra esta ventana y pulsa Verificar' }} para que aparezca al conectar ChatGPT.</p>
      <p v-if="grantsBusy" role="status" class="muted">Actualizando permisos…</p><div class="member-access" v-for="member in members" :key="member.id"><div><strong>{{ member.name }}</strong><small>{{ member.email }}{{ member.status === 'disabled' ? ' · Deshabilitado' : '' }}</small></div><div class="row-actions"><button class="button small" :class="hasAccess(member) ? 'soft' : 'secondary'" :disabled="grantsBusy || member.status !== 'active'" @click="toggleAccess(member)">{{ hasAccess(member) ? '✓ Lectura · Revocar' : 'Autorizar lectura' }}</button><button class="button small" :class="canSend(member) ? 'soft' : 'secondary'" :disabled="grantsBusy || member.status !== 'active' || !hasAccess(member) || (!permissions?.smtp_enabled && !canSend(member))" @click="toggleSending(member.membership_id)">{{ canSend(member) ? '✓ Envío · Revocar' : 'Autorizar envío' }}</button></div></div>
      <template #footer><button type="button" class="button secondary" :disabled="grantsBusy" @click="permissions = null">Cerrar</button></template>
    </AppModal>
    <AppModal :open="!!checking" :title="checkingSmtp ? 'Verificar envío SMTP' : 'Verificar conexión del buzón'" :description="checking?.email" size="small" :busy="busy" @close="checking = null">
      <p v-if="busy" role="status" class="notice">Comprobando la conexión segura con el servidor de correo…</p>
      <p v-else-if="checkError" role="alert" class="notice error">{{ checkError }}</p>
      <p v-else role="status" class="notice success">{{ checkingSmtp ? 'Conexión SMTP verificada. No se envió ningún correo.' : 'Conexión verificada. El buzón está listo para lectura.' }}</p>
      <template #footer><button v-if="checkError" type="button" class="button primary" :disabled="busy" @click="checking && check(checking, checkingSmtp)">Reintentar</button><button type="button" class="button secondary" :disabled="busy" @click="checking = null">Cerrar</button></template>
    </AppModal>
    <ConfirmModal :open="!!statusTarget" :title="statusTarget?.status === 'disabled' ? 'Habilitar buzón' : 'Deshabilitar buzón'"
      :message="statusTarget?.status === 'disabled' ? 'El buzón quedará pendiente de verificar antes de consultar sus correos.' : 'Los clientes dejarán de poder consultar este buzón hasta que vuelvas a habilitarlo.'"
      :confirm-label="statusTarget?.status === 'disabled' ? 'Habilitar' : 'Deshabilitar'" :busy="busy" :error="statusError"
      @close="statusTarget = null" @confirm="statusTarget && changeStatus(statusTarget)" />
    <section class="card management-panel mailbox-panel">
      <div class="panel-context"><div><span class="context-label">Empresa seleccionada</span><h2><AppIcon name="building" :size="20" />{{ tenant.name }}</h2></div><button type="button" class="button secondary small" :disabled="loading" @click="load"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
      <div class="table-toolbar"><label class="filter-search"><span class="sr-only">Buscar buzón</span><AppIcon name="search" :size="19" /><input v-model="query" type="search" maxlength="200" placeholder="Buscar nombre o correo del buzón" /></label><label class="filter-select"><span class="sr-only">Filtrar buzones por estado</span><select v-model="stateFilter"><option value="">Todos los estados</option><option value="active">Activos</option><option value="pending">Por verificar</option><option value="disabled">Deshabilitados</option></select></label></div>
      <div v-if="loading" class="empty-state" role="status">Cargando buzones…</div>
      <div v-else-if="!filteredMailboxes.length" class="empty-state panel-empty"><span class="empty-icon"><AppIcon name="mail" :size="29" /></span><h3>{{ mailboxes.length ? 'No se encontraron buzones' : 'Conecta tu primer buzón' }}</h3><p>{{ mailboxes.length ? 'Prueba con otro nombre, correo o estado.' : 'Agrega una cuenta corporativa para empezar a consultar sus mensajes.' }}</p><button v-if="mailboxes.length" type="button" class="text-button" @click="query = ''; stateFilter = ''">Limpiar filtros</button><button v-else-if="canManage" type="button" class="button primary" @click="openForm()"><AppIcon name="plus" :size="17" />Conectar buzón</button></div>
      <div v-else class="mailbox-list"><article v-for="mailbox in filteredMailboxes" :key="mailbox.id" class="mailbox-row"><span class="mailbox-icon"><AppIcon name="mail" :size="22" /></span><div class="mailbox-info"><strong>{{ mailbox.display_name }}</strong><span>{{ mailbox.email }}</span><small>{{ mailbox.imap_host }}:{{ mailbox.imap_port }} · TLS</small></div><span class="badge" :class="mailbox.status">{{ statusName(mailbox.status) }}</span><div class="row-actions"><button v-if="mailbox.can_read && mailbox.status === 'active'" class="button primary small" @click="reading = mailbox">Abrir →</button><button v-if="canManage && mailbox.can_read && mailbox.status !== 'disabled'" class="button secondary small" :disabled="busy" @click="check(mailbox)">{{ busy ? 'Espera…' : 'Verificar' }}</button><button v-if="canManage && mailbox.smtp_enabled && mailbox.can_read" class="button secondary small" :disabled="busy" @click="check(mailbox, true)">Verificar SMTP</button><button v-if="canManage" class="button secondary small" @click="openPermissions(mailbox)">Permisos</button><button v-if="canManage" class="text-button" @click="openForm(mailbox)">Editar</button><button v-if="canManage" class="text-button muted" :disabled="busy" @click="statusTarget = mailbox; statusError = ''">{{ mailbox.status === 'disabled' ? 'Habilitar' : 'Deshabilitar' }}</button><small v-if="!mailbox.can_read" class="muted">Sin permiso de lectura</small></div></article></div>
    </section>
  </div>
</template>

<style scoped>
.mailbox-password-field { min-width: 0; }
</style>
