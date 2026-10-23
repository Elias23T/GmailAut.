<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, ApiError, messageOf, type ClientAccount, type GlobalClient, type Tenant } from '../api'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import AppIcon from './AppIcon.vue'
import ConnectionsView from './ConnectionsView.vue'
import PasswordInput from './PasswordInput.vue'
const props = defineProps<{ tenant?: Tenant; tenants: Tenant[] }>()
const emit = defineEmits<{ select: [id: string]; manageCompanies: [] }>()
const companyRequired = ref(false)
const section = ref<'clients' | 'connections'>('clients')
const clients = ref<GlobalClient[]>([]), loading = ref(true), busy = ref(false), showForm = ref(false), error = ref(''), notice = ref('')
const form = reactive({ name: '', email: '', username: '', password: '' })
const credentialsTarget = ref<GlobalClient | null>(null), credentialsError = ref('')
const deleteTarget = ref<GlobalClient | null>(null), deleteError = ref('')
const bulkDeleteIds = ref<string[]>([]), bulkDeleteError = ref('')
const linkTarget = ref<GlobalClient | null>(null), linkTenant = ref<Tenant | null>(null), linkError = ref('')
const credentials = reactive({ username: '', password: '' })
const existing = ref(false), query = ref(''), stateFilter = ref('')
const activeCount = computed(() => clients.value.filter(client => client.status === 'active').length)
const disabledCount = computed(() => clients.value.filter(client => client.status === 'disabled').length)
const filteredClients = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('es')
  return clients.value.filter(client => (!stateFilter.value || client.status === stateFilter.value)
    && (!term || (client.name + ' ' + (client.email || '') + ' ' + (client.username || '')).toLocaleLowerCase('es').includes(term)))
})
const formError = ref(''), statusError = ref(''), statusTarget = ref<GlobalClient | null>(null)
const availableClients = ref<ClientAccount[]>([]), availableLoading = ref(false), availableError = ref(''), duplicateAccount = ref(false)
let loadRequest = 0
let availableRequest = 0
function openForm(existingAccount = false) {
  if (!props.tenant) { companyRequired.value = true; return }
  Object.assign(form, { name: '', email: '', username: '', password: '' }); existing.value = existingAccount; formError.value = ''; showForm.value = true
  duplicateAccount.value = false; availableClients.value = []; availableError.value = ''
  if (existingAccount) void loadAvailable()
}
function closeForm() { ++availableRequest; availableLoading.value = false; showForm.value = false; form.password = ''; formError.value = ''; duplicateAccount.value = false }
async function loadAvailable() {
  const tenant = props.tenant
  if (!tenant) return
  const request = ++availableRequest
  availableLoading.value = true; availableError.value = ''
  try {
    const result = await api<ClientAccount[]>(`/admin/clients/available?tenant_id=${tenant.id}`)
    if (request !== availableRequest) return
    availableClients.value = result
    if (!result.some(client => client.email.toLowerCase() === form.email.toLowerCase())) form.email = ''
    else form.email = result.find(client => client.email.toLowerCase() === form.email.toLowerCase())!.email
  } catch (cause) { if (request === availableRequest) availableError.value = messageOf(cause) }
  finally { if (request === availableRequest) availableLoading.value = false }
}
function changeAccessType() {
  form.password = ''; formError.value = ''; duplicateAccount.value = false
  if (existing.value) void loadAvailable()
  else { ++availableRequest; availableLoading.value = false }
}
function findAccount() {
  const term = form.username || form.email
  closeForm(); query.value = term; stateFilter.value = ''; void load()
}
async function load() {
  const request = ++loadRequest
  loading.value = true; error.value = ''
  try {
    const result = await api<GlobalClient[]>('/admin/clients/all')
    if (request === loadRequest) clients.value = result
  }
  catch (cause) { if (request === loadRequest) error.value = messageOf(cause) }
  finally { if (request === loadRequest) loading.value = false }
}
async function create() {
  const tenant = props.tenant
  if (!tenant) { companyRequired.value = true; return }
  if (busy.value) return
  if (existing.value && (availableLoading.value || !availableClients.value.some(client => client.email === form.email))) {
    formError.value = 'Selecciona una cuenta existente para vincularla a esta empresa.'; return
  }
  const linking = existing.value
  busy.value = true; formError.value = ''; notice.value = ''; duplicateAccount.value = false
  try {
    await api(existing.value ? '/admin/clients/link' : '/admin/clients', 'POST', existing.value
      ? { email: form.email, tenant_id: tenant.id } : { ...form, tenant_id: tenant.id })
    Object.assign(form, { name: '', email: '', username: '', password: '' }); showForm.value = false
    notice.value = linking
      ? 'Cliente vinculado a esta empresa.'
      : 'Cliente agregado.'
    await load()
  } catch (cause) {
    formError.value = messageOf(cause)
    duplicateAccount.value = !existing.value && cause instanceof ApiError && cause.status === 409
  }
  finally { busy.value = false }
}
async function toggle(client: GlobalClient) {
  if (busy.value) return
  busy.value = true; statusError.value = ''
  try {
    await api(`/admin/clients/${client.id}/status`, 'PATCH', { status: client.status === 'active' ? 'disabled' : 'active' })
    statusTarget.value = null
    notice.value = client.status === 'active' ? 'Cliente suspendido y conexiones revocadas.' : 'Cliente activado. Puede volver a autorizar ChatGPT.'
    await load()
  } catch (cause) { statusError.value = messageOf(cause) }
  finally { busy.value = false }
}
function openCredentials(client: GlobalClient) {
  credentialsTarget.value = client; credentialsError.value = ''
  credentials.username = client.username || ''; credentials.password = ''
}
function closeCredentials() { credentialsTarget.value = null; credentials.password = ''; credentialsError.value = '' }
async function saveCredentials() {
  if (busy.value || !credentialsTarget.value) return
  busy.value = true; credentialsError.value = ''; notice.value = ''
  try {
    await api(`/admin/clients/${credentialsTarget.value.id}/credentials`, 'PATCH', {
      username: credentials.username, ...(credentials.password ? { password: credentials.password } : {}),
    })
    closeCredentials()
    notice.value = 'Acceso guardado.'
    await load()
  } catch (cause) { credentialsError.value = messageOf(cause) }
  finally { busy.value = false }
}
function askLink(client: GlobalClient) {
  if (!props.tenant) { companyRequired.value = true; return }
  linkTarget.value = client; linkTenant.value = props.tenant; linkError.value = ''
}
async function linkClient() {
  if (busy.value || !linkTarget.value || !linkTenant.value) return
  busy.value = true; linkError.value = ''; notice.value = ''
  try {
    await api('/admin/clients/link', 'POST', { tenant_id: linkTenant.value.id, email: linkTarget.value.email })
    notice.value = `Cliente vinculado a ${linkTenant.value.name}. Conserva su contraseña y estado. Asigna sus buzones desde Permisos.`
    linkTarget.value = null; await load()
  } catch (cause) { linkError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function removeClient() {
  if (busy.value || !deleteTarget.value) return
  busy.value = true; deleteError.value = ''; notice.value = ''
  try {
    await api(`/admin/clients/${deleteTarget.value.id}`, 'DELETE')
    deleteTarget.value = null; notice.value = 'Cliente eliminado. Su usuario y correo ya pueden utilizarse en una cuenta nueva.'; await load()
  } catch (cause) { deleteError.value = messageOf(cause) }
  finally { busy.value = false }
}
function closeBulkDelete() { bulkDeleteIds.value = []; bulkDeleteError.value = '' }
function askBulkDelete() {
  if (loading.value || busy.value || error.value) return
  bulkDeleteIds.value = clients.value.filter(client => client.status === 'disabled').map(client => client.id)
  bulkDeleteError.value = ''
}
async function removeDisabledClients() {
  if (busy.value || !bulkDeleteIds.value.length) return
  busy.value = true; bulkDeleteError.value = ''; notice.value = ''
  try {
    const result = await api<{ deleted_count: number }>('/admin/clients/delete-disabled', 'POST', {
      user_ids: bulkDeleteIds.value, confirmed: true,
    })
    closeBulkDelete()
    notice.value = `Clientes suspendidos eliminados: ${result.deleted_count}. Las cuentas habilitadas y el historial de auditoría se conservan.`
    await load()
  } catch (cause) { bulkDeleteError.value = messageOf(cause) }
  finally { busy.value = false }
}
watch(() => props.tenant?.id, () => {
  closeForm(); closeCredentials(); closeBulkDelete(); statusTarget.value = null; deleteTarget.value = null; linkTarget.value = null; companyRequired.value = false
}, { immediate: true })
onMounted(load)
</script>

<template>
  <div class="page-heading"><div><h1>Clientes y accesos</h1><p class="muted">Administra las cuentas de clientes de todas las empresas, incluidas las que están sin empresa.</p></div></div>
  <div class="section-tabs" aria-label="Funciones de clientes"><button type="button" :class="{ active: section === 'clients' }" :aria-pressed="section === 'clients'" aria-controls="authorized-clients-panel" @click="section = 'clients'">Clientes autorizados</button><button type="button" :class="{ active: section === 'connections' }" :aria-pressed="section === 'connections'" aria-controls="client-connections-panel" @click="section = 'connections'">Conexión ChatGPT</button></div>
  <div id="authorized-clients-panel" v-show="section === 'clients'">
  <div class="stats-grid stats-four">
    <div class="stat-card"><span>Clientes<AppIcon name="users" :size="19" /></span><strong>{{ clients.length }}</strong></div>
    <div class="stat-card"><span>Habilitados<AppIcon name="check" :size="19" /></span><strong class="metric-success">{{ activeCount }}</strong></div>
    <div class="stat-card"><span>Suspendidos<AppIcon name="warning" :size="19" /></span><strong class="metric-danger">{{ disabledCount }}</strong></div>
    <div class="stat-card"><span>Permiso de acceso<AppIcon name="shield" :size="19" /></span><strong class="metric-text">Por buzón</strong></div>
  </div>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <AppModal :open="showForm" :title="(existing ? 'Vincular cliente a ' : 'Agregar cliente a ') + (tenant?.name || '')" :busy="busy" @close="closeForm">
    <div v-if="formError" class="notice error" role="alert">{{ formError }} <button v-if="duplicateAccount" type="button" class="text-button" :disabled="busy" @click="findAccount">Buscar cuenta en el listado</button></div>
    <form id="client-form" @submit.prevent="create">
      <label>Tipo de acceso<select v-model="existing" :disabled="busy" @change="changeAccessType"><option :value="false">Crear una cuenta nueva</option><option :value="true">Vincular un cliente que ya existe</option></select></label>
      <template v-if="existing">
        <div v-if="availableError" class="notice error" role="alert">{{ availableError }} <button type="button" class="text-button" :disabled="availableLoading" @click="loadAvailable">Reintentar</button></div>
        <label>Clientes existentes disponibles
          <select v-model="form.email" required :disabled="busy || availableLoading || !availableClients.length">
            <option value="" disabled>{{ availableLoading ? 'Cargando cuentas…' : 'Selecciona un cliente' }}</option>
            <option v-for="client in availableClients" :key="client.id" :value="client.email">{{ client.name }} · {{ client.username || 'Acceso por correo' }} · {{ client.email }}{{ client.status === 'disabled' ? ' · Suspendido' : '' }}</option>
          </select>
        </label>
        <p v-if="availableLoading" class="muted" role="status">Buscando cuentas que todavía no están vinculadas a {{ tenant?.name }}…</p>
        <p v-else-if="!availableError && !availableClients.length" class="notice">No hay otras cuentas de cliente disponibles. Las cuentas ya vinculadas aparecen en el listado de esta empresa.</p>
      </template>
      <div v-else class="form-grid">
        <label>Nombre completo<input v-model="form.name" required maxlength="120" placeholder="Persona de ejemplo" :disabled="busy" /></label>
        <label>Correo del cliente<input v-model="form.email" type="email" required maxlength="320" autocomplete="off" placeholder="cliente@example.com" :disabled="busy" /></label>
        <label>Usuario del cliente<input v-model="form.username" required minlength="3" maxlength="32" pattern="[a-zA-Z][a-zA-Z0-9_.\-]{2,31}" autocomplete="off" placeholder="cliente01" :disabled="busy" /></label>
        <label>Crear contraseña para Corporate Mail AI<PasswordInput v-model="form.password" required minlength="6" maxlength="1024" :disabled="busy" autocomplete="new-password" placeholder="Crea una contraseña nueva" /></label>
      </div>
    </form>
    <template #footer><button type="button" class="button secondary" :disabled="busy" @click="closeForm">Cancelar</button><button form="client-form" type="submit" class="button primary" :disabled="busy || (existing && (availableLoading || !form.email || !!availableError))">{{ busy ? 'Guardando…' : existing ? 'Vincular cliente' : 'Agregar cliente' }}</button></template>
  </AppModal>
  <AppModal :open="!!credentialsTarget" title="Acceso del cliente a ChatGPT" :description="credentialsTarget?.name" :busy="busy" @close="closeCredentials">
    <p v-if="credentialsError" class="notice error" role="alert">{{ credentialsError }}</p>
    <form id="client-credentials-form" @submit.prevent="saveCredentials">
      <label>Usuario del cliente<input v-model="credentials.username" required minlength="3" maxlength="32" pattern="[a-zA-Z][a-zA-Z0-9_.\-]{2,31}" placeholder="cliente01" autocomplete="off" :disabled="busy" /></label>
      <label>Nueva contraseña de Corporate Mail AI<PasswordInput v-model="credentials.password" minlength="6" maxlength="1024" autocomplete="new-password" placeholder="Déjala vacía para conservar la actual" :disabled="busy" /></label>
      <p class="notice">Cambiar el acceso cierra sus sesiones y conexiones con ChatGPT.</p>
    </form>
    <template #footer><button type="button" class="button secondary" :disabled="busy" @click="closeCredentials">Cancelar</button><button type="submit" form="client-credentials-form" class="button primary" :disabled="busy">{{ busy ? 'Guardando…' : 'Guardar acceso' }}</button></template>
  </AppModal>
  <ConfirmModal :open="!!statusTarget" :title="statusTarget?.status === 'active' ? 'Suspender cliente' : 'Activar cliente'"
    :message="statusTarget?.status === 'active' ? 'Se suspenderá su acceso en todas las empresas y se revocarán sus conexiones con ChatGPT.' : 'El cliente podrá iniciar sesión y volver a autorizar la conexión con ChatGPT.'"
    :confirm-label="statusTarget?.status === 'active' ? 'Suspender acceso' : 'Activar cliente'" :busy="busy" :error="statusError"
    @close="statusTarget = null" @confirm="statusTarget && toggle(statusTarget)" />
  <ConfirmModal :open="!!deleteTarget" title="Eliminar cliente" :message="deleteTarget?.status === 'active' ? 'Primero suspende el acceso del cliente para poder eliminar su cuenta.' : 'La cuenta se retirará de todas sus empresas y se liberarán su usuario y correo. El historial de auditoría se conserva.'" confirm-label="Eliminar" danger :busy="busy" :error="deleteError" @close="deleteTarget = null" @confirm="removeClient" />
  <ConfirmModal :open="!!bulkDeleteIds.length" title="Eliminar clientes suspendidos"
    :message="`Se eliminarán ${bulkDeleteIds.length} cuentas suspendidas de todas las empresas, incluidas las que están sin empresa, aunque no aparezcan con los filtros actuales. Se liberarán sus usuarios y correos. Las cuentas habilitadas y el historial de auditoría se conservan. Esta acción no se puede deshacer.`"
    :confirm-label="`Eliminar ${bulkDeleteIds.length} cuentas`" danger :busy="busy" :error="bulkDeleteError" @close="closeBulkDelete" @confirm="removeDisabledClients" />
  <ConfirmModal :open="!!linkTarget" title="Vincular cliente existente" :message="`Vincularás esta cuenta a ${linkTenant?.name || 'la empresa seleccionada'}, conservando su contraseña y estado. Después asigna sus buzones desde Permisos.`" confirm-label="Vincular" :busy="busy" :error="linkError" @close="linkTarget = null" @confirm="linkClient" />

  <section class="card management-panel">
    <div class="panel-context"><label class="client-company-select" for="client-company">Empresa para agregar o vincular clientes<select id="client-company" :value="tenant?.id || ''" :disabled="!tenants.length || busy" @change="emit('select', ($event.target as HTMLSelectElement).value)"><option value="" disabled>{{ tenants.length ? 'Selecciona una empresa' : 'Sin empresas activas' }}</option><option v-for="company in tenants" :key="company.id" :value="company.id">{{ company.name }}</option></select><small>El listado muestra clientes de todas las empresas y sin empresa.</small></label><button type="button" class="button secondary small" :disabled="loading || busy" @click="load"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
    <div class="table-toolbar">
      <label class="filter-search"><span class="sr-only">Buscar cliente por nombre, usuario o correo</span><AppIcon name="search" :size="19" /><input v-model="query" placeholder="Buscar nombre, usuario o correo" type="search" maxlength="200" /></label>
      <label class="filter-select"><span class="sr-only">Filtrar clientes por estado</span><select v-model="stateFilter"><option value="">Todos los estados</option><option value="active">Habilitados</option><option value="disabled">Suspendidos</option></select></label>
      <button type="button" class="button secondary" :disabled="loading || busy || !!error || !disabledCount" @click="askBulkDelete">Eliminar clientes suspendidos</button>
      <div class="toolbar-actions"><button type="button" class="button primary" @click="openForm(false)"><AppIcon name="plus" :size="18" />Agregar cliente</button><button type="button" class="button secondary" @click="openForm(true)">Vincular</button></div>
    </div>
    <div v-if="loading" class="empty-state" role="status">Cargando clientes…</div>
    <div v-else-if="!filteredClients.length" class="empty-state panel-empty"><span class="empty-icon"><AppIcon name="users" :size="29" /></span><h3>{{ clients.length ? 'No se encontraron clientes' : 'Todavía no hay clientes' }}</h3><p>{{ clients.length ? 'Prueba con otro nombre, usuario, correo o estado.' : tenants.length ? 'Agrega tu primer cliente y configura sus buzones y permisos.' : 'Primero crea o activa una empresa para agregar clientes.' }}</p><button v-if="clients.length" type="button" class="text-button" @click="query = ''; stateFilter = ''">Limpiar filtros</button><button v-else-if="!tenants.length" type="button" class="button secondary" @click="emit('manageCompanies')">Ir a Empresas</button></div>
    <div v-else class="table-scroll client-table"><table><thead><tr><th>Cliente</th><th>Correo de acceso</th><th>Empresas</th><th>Estado</th><th class="actions-column">Acciones</th></tr></thead><tbody>
      <tr v-for="client in filteredClients" :key="client.id"><td><div class="table-person"><span class="person-avatar">{{ client.name.slice(0, 1).toUpperCase() }}</span><div><strong>{{ client.name }}</strong><small class="muted"> · {{ client.username || 'Acceso por correo' }}</small></div></div></td><td>{{ client.email || 'Sin correo' }}</td><td>{{ client.companies.map(company => company.name + (company.status !== 'active' ? ' (desactivada)' : '')).join(', ') || 'Sin empresa' }}</td><td><span class="badge" :class="client.status"><span class="badge-dot"></span>{{ client.status === 'active' ? 'Habilitado' : 'Suspendido' }}</span></td><td class="actions-column"><div class="row-actions"><button v-if="tenant && client.email && !client.companies.some(company => company.id === tenant?.id)" type="button" class="button secondary small" :disabled="busy" @click="askLink(client)">Vincular a {{ tenant.name }}</button><button type="button" class="button secondary small" :disabled="busy" @click="openCredentials(client)">Configurar acceso</button><button type="button" class="button secondary small" :disabled="busy" @click="statusTarget = client; statusError = ''">{{ client.status === 'active' ? 'Suspender acceso' : 'Activar cliente' }}</button><button type="button" class="button secondary small" :disabled="busy" @click="deleteTarget = client; deleteError = ''">Eliminar</button></div></td></tr>
    </tbody></table></div>
    <div v-if="!loading && filteredClients.length" class="panel-bottom"><span>{{ filteredClients.length }} de {{ clients.length }} clientes</span><span>Acceso administrado por la plataforma</span></div>
  </section>
  </div>
  <div v-if="section === 'connections'" id="client-connections-panel">
    <div class="workspace-company"><label for="connection-company">Empresa seleccionada<select id="connection-company" :value="tenant?.id || ''" :disabled="!tenants.length" @change="emit('select', ($event.target as HTMLSelectElement).value)"><option value="" disabled>{{ tenants.length ? 'Selecciona una empresa' : 'Sin empresas activas' }}</option><option v-for="company in tenants" :key="company.id" :value="company.id">{{ company.name }}</option></select></label><button type="button" class="text-button" @click="emit('manageCompanies')">Administrar empresas</button></div>
    <ConnectionsView :key="tenant?.id || 'no-company'" :tenant="tenant" />
  </div>
  <AppModal :open="companyRequired" title="Primero selecciona una empresa" size="small" @close="companyRequired = false"><p>{{ tenants.length ? 'Selecciona una empresa en el listado de Clientes antes de agregar o vincular una cuenta.' : 'No hay empresas activas. Primero crea una empresa o activa una existente para poder agregar o vincular clientes.' }}</p><template #footer><button type="button" class="button secondary" @click="companyRequired = false">Cerrar</button><button type="button" class="button primary" @click="companyRequired = false; emit('manageCompanies')">Ir a Empresas</button></template></AppModal>
</template>
