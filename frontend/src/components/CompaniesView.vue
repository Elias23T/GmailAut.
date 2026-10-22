<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, messageOf, type Tenant } from '../api'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'

const props = defineProps<{ tenants: Tenant[]; selectedId: string; loading: boolean }>()
const emit = defineEmits<{ updated: [tenant: Tenant]; removed: [id: string]; select: [id: string]; refresh: [] }>()
const query = ref(''), stateFilter = ref(''), showForm = ref(false), busy = ref(false)
const editing = ref<Tenant | null>(null), target = ref<Tenant | null>(null)
const operation = ref<'status' | 'delete'>('status'), blocked = ref(''), error = ref(''), notice = ref('')
const form = reactive({ name: '' })
const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('es')
  return props.tenants.filter(tenant => (!stateFilter.value || tenant.status === stateFilter.value)
    && (!term || tenant.name.toLocaleLowerCase('es').includes(term)))
})
const activeCount = computed(() => props.tenants.filter(tenant => tenant.status === 'active').length)
const disabledCount = computed(() => props.tenants.filter(tenant => tenant.status === 'disabled').length)
function openForm(tenant: Tenant | null = null) {
  editing.value = tenant; form.name = tenant?.name || ''
  error.value = ''; showForm.value = true
}
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const tenant = await api<Tenant>(editing.value ? `/tenants/${editing.value.id}` : '/tenants', editing.value ? 'PATCH' : 'POST', form)
    emit('updated', tenant); showForm.value = false
    notice.value = editing.value ? 'Empresa actualizada.' : 'Empresa creada. Puedes seleccionarla para administrar sus buzones y clientes.'
  } catch (cause) { error.value = messageOf(cause) }
  finally { busy.value = false }
}
function confirm(tenant: Tenant, action: 'status' | 'delete') {
  error.value = ''
  if (action === 'delete' && tenant.status !== 'disabled') {
    blocked.value = `No se puede eliminar la empresa «${tenant.name}» porque está ${tenant.status === 'active' ? 'activa' : 'suspendida'}. Primero desactívala y vuelve a intentar la eliminación.`
    return
  }
  target.value = tenant; operation.value = action
}
const title = computed(() => operation.value === 'delete' ? 'Eliminar empresa' : target.value?.status === 'disabled' ? 'Activar empresa' : 'Desactivar empresa')
const confirmation = computed(() => operation.value === 'delete'
  ? `Se eliminará definitivamente «${target.value?.name}» junto con sus buzones, credenciales, permisos, membresías, autorizaciones y actividad. Las cuentas de clientes y los correos de su proveedor se conservarán. Esta acción no se puede deshacer.`
  : target.value?.status === 'disabled' ? `Se habilitará «${target.value.name}». Los clientes necesitarán volver a autorizar sus conexiones con ChatGPT.`
    : `Se desactivará «${target.value?.name}»: se bloqueará el acceso a sus buzones y se revocarán sus conexiones con ChatGPT. Sus datos se conservarán.`)
async function execute() {
  const tenant = target.value
  if (!tenant || busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (operation.value === 'delete') {
      await api(`/tenants/${tenant.id}`, 'DELETE'); emit('removed', tenant.id); notice.value = 'Empresa y datos relacionados eliminados.'
    } else {
      const updated = await api<Tenant>(`/tenants/${tenant.id}/status`, 'PATCH', { status: tenant.status === 'disabled' ? 'active' : 'disabled' })
      emit('updated', updated); notice.value = updated.status === 'active' ? 'Empresa activada.' : 'Empresa desactivada y conexiones revocadas.'
    }
    target.value = null
  } catch (cause) { error.value = messageOf(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <div class="page-heading"><div><h1>Empresas</h1><p class="muted">Crea y administra las empresas de tus clientes.</p></div></div>
  <div class="stats-grid">
    <div class="stat-card"><span>Empresas<AppIcon name="building" :size="19" /></span><strong>{{ tenants.length }}</strong></div>
    <div class="stat-card"><span>Activas<AppIcon name="check" :size="19" /></span><strong class="metric-success">{{ activeCount }}</strong></div>
    <div class="stat-card"><span>Desactivadas<AppIcon name="warning" :size="19" /></span><strong class="metric-danger">{{ disabledCount }}</strong></div>
  </div>
  <p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <section class="card management-panel">
    <div class="panel-context"><div><span class="context-label">Administración</span><h2><AppIcon name="building" :size="20" />Listado de empresas</h2></div><button type="button" class="button secondary small" :disabled="loading || busy" @click="emit('refresh')"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
    <div class="table-toolbar">
      <label class="filter-search"><span class="sr-only">Buscar empresa</span><AppIcon name="search" :size="19" /><input v-model="query" type="search" placeholder="Buscar empresa por nombre" maxlength="200" /></label>
      <label class="filter-select"><span class="sr-only">Filtrar empresas por estado</span><select v-model="stateFilter"><option value="">Todos los estados</option><option value="active">Activas</option><option value="disabled">Desactivadas</option><option value="suspended">Suspendidas</option></select></label>
      <div class="toolbar-actions"><button type="button" class="button primary" :disabled="busy" @click="openForm()"><AppIcon name="plus" :size="18" />Crear empresa</button></div>
    </div>
    <div v-if="loading" class="empty-state" role="status">Cargando empresas…</div>
    <div v-else-if="!filtered.length" class="empty-state panel-empty"><span class="empty-icon"><AppIcon name="building" :size="29" /></span><h3>{{ tenants.length ? 'No se encontraron empresas' : 'Crea tu primera empresa' }}</h3><p>{{ tenants.length ? 'Prueba con otro nombre o estado.' : 'Usa Crear empresa para organizar sus buzones y clientes.' }}</p><button v-if="tenants.length" type="button" class="text-button" @click="query = ''; stateFilter = ''">Limpiar filtros</button></div>
    <div v-else class="table-scroll company-table"><table><thead><tr><th>Empresa</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
      <tr v-for="tenant in filtered" :key="tenant.id"><td><strong>{{ tenant.name }}</strong><small v-if="selectedId === tenant.id && tenant.status === 'active'" class="company-selected">Seleccionada</small></td><td><span class="badge" :class="tenant.status"><span class="badge-dot"></span>{{ tenant.status === 'active' ? 'Activa' : tenant.status === 'disabled' ? 'Desactivada' : 'Suspendida' }}</span></td><td><div class="company-actions">
        <button v-if="tenant.status === 'active'" type="button" class="button secondary small" :disabled="busy" @click="emit('select', tenant.id)">Usar empresa</button>
        <button type="button" class="button secondary small" :disabled="busy" @click="openForm(tenant)">Editar</button>
        <button type="button" class="button secondary small" :disabled="busy" @click="confirm(tenant, 'status')">{{ tenant.status === 'disabled' ? 'Activar' : 'Desactivar' }}</button>
        <button type="button" class="button secondary small danger-text" :disabled="busy" @click="confirm(tenant, 'delete')">Eliminar</button>
      </div></td></tr>
    </tbody></table></div>
    <div v-if="!loading && filtered.length" class="panel-bottom"><span>{{ filtered.length }} de {{ tenants.length }} empresas</span><span>Solo se pueden eliminar empresas desactivadas</span></div>
  </section>
  <AppModal :open="showForm" :title="editing ? 'Editar empresa' : 'Nueva empresa'" description="Organiza sus clientes y buzones en un mismo espacio." :busy="busy" @close="showForm = false">
    <form id="company-form" @submit.prevent="save">
      <p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <label>Nombre<input v-model="form.name" required maxlength="120" placeholder="Mi empresa" /></label>
    </form>
    <template #footer><button type="button" class="button secondary" :disabled="busy" @click="showForm = false">Cancelar</button><button form="company-form" type="submit" class="button primary" :disabled="busy">{{ busy ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear empresa' }}</button></template>
  </AppModal>
  <ConfirmModal :open="!!target" :title="title" :message="confirmation" :confirm-label="title" :busy="busy" :error="error" :danger="operation === 'delete'" @close="target = null" @confirm="execute" />
  <AppModal :open="!!blocked" title="No se puede eliminar la empresa" size="small" @close="blocked = ''"><p class="notice error" role="alert">{{ blocked }}</p><template #footer><button type="button" class="button primary" @click="blocked = ''">Entendido</button></template></AppModal>
</template>
