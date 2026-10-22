<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, messageOf, type Client, type Tenant } from '../api'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import AppIcon from './AppIcon.vue'
import ConnectionsView from './ConnectionsView.vue'
const props = defineProps<{ tenant?: Tenant; tenants: Tenant[] }>()
const emit = defineEmits<{ select: [id: string]; manageCompanies: [] }>()
const companyRequired = ref(false)
const section = ref<'clients' | 'connections'>('clients')
const clients = ref<Client[]>([]), loading = ref(true), busy = ref(false), showForm = ref(false), error = ref(''), notice = ref('')
const form = reactive({ name: '', email: '', password: '' })
const existing = ref(false), query = ref(''), stateFilter = ref('')
const activeCount = computed(() => clients.value.filter(client => client.status === 'active').length)
const disabledCount = computed(() => clients.value.filter(client => client.status === 'disabled').length)
const filteredClients = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('es')
  return clients.value.filter(client => (!stateFilter.value || client.status === stateFilter.value)
    && (!term || (client.name + ' ' + client.email).toLocaleLowerCase('es').includes(term)))
})
const formError = ref(''), statusError = ref(''), statusTarget = ref<Client | null>(null)
let loadRequest = 0
function openForm(existingAccount = false) {
  if (!props.tenant) { companyRequired.value = true; return }
  Object.assign(form, { name: '', email: '', password: '' }); existing.value = existingAccount; formError.value = ''; showForm.value = true
}
function closeForm() { showForm.value = false; form.password = ''; formError.value = '' }
async function load() {
  const request = ++loadRequest
  const tenant = props.tenant
  if (!tenant) { clients.value = []; loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    const result = await api<Client[]>(`/admin/clients?tenant_id=${tenant.id}`)
    if (request === loadRequest) clients.value = result
  }
  catch (cause) { if (request === loadRequest) error.value = messageOf(cause) }
  finally { if (request === loadRequest) loading.value = false }
}
async function create() {
  const tenant = props.tenant
  if (!tenant) { companyRequired.value = true; return }
  if (busy.value) return
  busy.value = true; formError.value = ''; notice.value = ''
  try {
    await api(existing.value ? '/admin/clients/link' : '/admin/clients', 'POST', existing.value
      ? { email: form.email, tenant_id: tenant.id } : { ...form, tenant_id: tenant.id })
    Object.assign(form, { name: '', email: '', password: '' }); showForm.value = false
    notice.value = 'Cliente agregado. Asigna sus buzones desde Buzones → Permisos. Para cuentas nuevas, entrega sus datos de acceso por un canal privado.'
    await load()
  } catch (cause) { formError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function toggle(client: Client) {
  const tenant = props.tenant
  if (!tenant) { companyRequired.value = true; return }
  if (busy.value) return
  busy.value = true; statusError.value = ''
  try {
    await api(`/admin/clients/${client.id}?tenant_id=${tenant.id}`, 'PATCH', { status: client.status === 'active' ? 'disabled' : 'active' })
    statusTarget.value = null
    notice.value = client.status === 'active' ? 'Cliente suspendido y conexiones revocadas.' : 'Cliente activado. Puede volver a autorizar ChatGPT.'
    await load()
  } catch (cause) { statusError.value = messageOf(cause) }
  finally { busy.value = false }
}
watch(() => props.tenant?.id, () => {
  clients.value = []; error.value = ''; notice.value = ''; query.value = ''; stateFilter.value = ''
  closeForm(); statusTarget.value = null; companyRequired.value = false
  void load()
}, { immediate: true })
</script>

<template>
  <div class="page-heading"><div><h1>Clientes y accesos</h1><p class="muted">Administra quién puede consultar los correos de tu empresa.</p></div></div>
  <div class="section-tabs" aria-label="Funciones de clientes"><button type="button" :class="{ active: section === 'clients' }" :aria-pressed="section === 'clients'" aria-controls="authorized-clients-panel" @click="section = 'clients'">Clientes autorizados</button><button type="button" :class="{ active: section === 'connections' }" :aria-pressed="section === 'connections'" aria-controls="client-connections-panel" @click="section = 'connections'">Conexión ChatGPT</button></div>
  <div id="authorized-clients-panel" v-show="section === 'clients'">
  <div class="stats-grid stats-four">
    <div class="stat-card"><span>Clientes<AppIcon name="users" :size="19" /></span><strong>{{ clients.length }}</strong></div>
    <div class="stat-card"><span>Habilitados<AppIcon name="check" :size="19" /></span><strong class="metric-success">{{ activeCount }}</strong></div>
    <div class="stat-card"><span>Suspendidos<AppIcon name="warning" :size="19" /></span><strong class="metric-danger">{{ disabledCount }}</strong></div>
    <div class="stat-card"><span>Permiso de acceso<AppIcon name="shield" :size="19" /></span><strong class="metric-text">Solo lectura</strong></div>
  </div>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <AppModal :open="showForm" :title="(existing ? 'Vincular cliente a ' : 'Agregar cliente a ') + (tenant?.name || '')" :description="existing ? 'Indica el correo de una cuenta existente para darle acceso a esta empresa.' : 'Crea una cuenta de cliente para autorizar el acceso a sus buzones.'" :busy="busy" @close="closeForm">
    <p v-if="formError" class="notice error" role="alert">{{ formError }}</p>
    <form id="client-form" @submit.prevent="create"><label>Tipo de acceso<select v-model="existing" @change="form.password = ''"><option :value="false">Crear una cuenta nueva</option><option :value="true">Vincular un cliente que ya existe</option></select></label><div class="form-grid"><label v-if="!existing">Nombre completo<input v-model="form.name" required maxlength="120" placeholder="Persona de ejemplo" /></label><label>Correo de acceso<input v-model="form.email" type="email" required maxlength="320" autocomplete="off" placeholder="cliente@example.com" /></label><label v-if="!existing">Contraseña de la plataforma<input v-model="form.password" type="password" required minlength="12" maxlength="1024" autocomplete="new-password" placeholder="Al menos 12 caracteres" /></label></div></form>
    <p class="muted modal-hint">Esta cuenta permite autorizar ChatGPT. El administrador configura sus buzones.</p>
    <template #footer><button type="button" class="button secondary" :disabled="busy" @click="closeForm">Cancelar</button><button form="client-form" type="submit" class="button primary" :disabled="busy">{{ busy ? 'Guardando…' : existing ? 'Vincular cliente' : 'Agregar cliente' }}</button></template>
  </AppModal>
  <ConfirmModal :open="!!statusTarget" :title="statusTarget?.status === 'active' ? 'Suspender cliente' : 'Activar cliente'"
    :message="statusTarget?.status === 'active' ? 'Se suspenderá su acceso y se revocarán sus conexiones con ChatGPT.' : 'El cliente podrá iniciar sesión y volver a autorizar la conexión con ChatGPT.'"
    :confirm-label="statusTarget?.status === 'active' ? 'Suspender acceso' : 'Activar cliente'" :busy="busy" :error="statusError"
    @close="statusTarget = null" @confirm="statusTarget && toggle(statusTarget)" />

  <section class="card management-panel">
    <div class="panel-context"><label class="client-company-select" for="client-company">Empresa seleccionada<select id="client-company" :value="tenant?.id || ''" :disabled="!tenants.length || busy" @change="emit('select', ($event.target as HTMLSelectElement).value)"><option value="" disabled>{{ tenants.length ? 'Selecciona una empresa' : 'Sin empresas activas' }}</option><option v-for="company in tenants" :key="company.id" :value="company.id">{{ company.name }}</option></select></label><button type="button" class="button secondary small" :disabled="loading || !tenant" @click="load"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
    <div class="table-toolbar">
      <label class="filter-search"><span class="sr-only">Buscar cliente por nombre o correo</span><AppIcon name="search" :size="19" /><input v-model="query" placeholder="Buscar nombre o correo" type="search" maxlength="200" /></label>
      <label class="filter-select"><span class="sr-only">Filtrar clientes por estado</span><select v-model="stateFilter"><option value="">Todos los estados</option><option value="active">Habilitados</option><option value="disabled">Suspendidos</option></select></label>
      <div class="toolbar-actions"><button type="button" class="button primary" @click="openForm(false)"><AppIcon name="plus" :size="18" />Agregar cliente</button><button type="button" class="button secondary" @click="openForm(true)">Vincular</button></div>
    </div>
    <div v-if="loading" class="empty-state" role="status">Cargando clientes…</div>
    <div v-else-if="!tenant" class="empty-state panel-empty"><span class="empty-icon"><AppIcon name="building" :size="29" /></span><h3>{{ tenants.length ? 'Selecciona una empresa' : 'Todavía no hay empresas activas' }}</h3><p>{{ tenants.length ? 'Elige una empresa en el selector para consultar y agregar sus clientes.' : 'Para agregar o vincular clientes, primero crea una empresa o activa una existente desde Empresas.' }}</p><button type="button" class="button secondary" @click="emit('manageCompanies')">Ir a Empresas</button></div>
    <div v-else-if="!filteredClients.length" class="empty-state panel-empty"><span class="empty-icon"><AppIcon name="users" :size="29" /></span><h3>{{ clients.length ? 'No se encontraron clientes' : 'Agrega tu primer cliente' }}</h3><p>{{ clients.length ? 'Prueba con otro nombre, correo o estado.' : 'Crea una cuenta o vincula un cliente existente. Después podrás autorizar sus buzones.' }}</p><button v-if="clients.length" type="button" class="text-button" @click="query = ''; stateFilter = ''">Limpiar filtros</button></div>
    <div v-else class="table-scroll client-table"><table><thead><tr><th>Cliente</th><th>Correo de acceso</th><th>Estado</th><th class="actions-column">Acciones</th></tr></thead><tbody>
      <tr v-for="client in filteredClients" :key="client.id"><td><div class="table-person"><span class="person-avatar">{{ client.name.slice(0, 1).toUpperCase() }}</span><strong>{{ client.name }}</strong></div></td><td>{{ client.email }}</td><td><span class="badge" :class="client.status"><span class="badge-dot"></span>{{ client.status === 'active' ? 'Habilitado' : 'Suspendido' }}</span></td><td class="actions-column"><button type="button" class="button secondary small" :disabled="busy" @click="statusTarget = client; statusError = ''">{{ client.status === 'active' ? 'Suspender acceso' : 'Activar cliente' }}</button></td></tr>
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
