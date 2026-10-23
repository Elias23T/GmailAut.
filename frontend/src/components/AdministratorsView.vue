<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, messageOf, type User } from '../api'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import PasswordInput from './PasswordInput.vue'

const props = defineProps<{ currentUser: User }>()
const emit = defineEmits<{ updated: [user: User]; logout: [] }>()
const administrators = ref<User[]>([]), loading = ref(true), busy = ref(false)
const error = ref(''), notice = ref(''), showForm = ref(false), formError = ref('')
const statusTarget = ref<User | null>(null), statusError = ref(''), query = ref(''), stateFilter = ref('')
const editingTarget = ref<User | null>(null), deleteTarget = ref<User | null>(null), deleteError = ref(''), needsLogin = ref(false)
const form = reactive({ name: '', username: '', email: '', password: '' })
const activeCount = computed(() => administrators.value.filter(user => user.status === 'active').length)
const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('es')
  return administrators.value.filter(user => (!stateFilter.value || user.status === stateFilter.value)
    && (!term || `${user.name} ${user.username || ''} ${user.email || ''}`.toLocaleLowerCase('es').includes(term)))
})
async function load() {
  loading.value = true; error.value = ''
  try { administrators.value = await api<User[]>('/admin/administrators') }
  catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
function openForm(user?: User) {
  editingTarget.value = user || null
  Object.assign(form, { name: user?.name || '', username: user?.username || '', email: user?.email || '', password: '' })
  formError.value = ''; showForm.value = true
}
function closeForm() { showForm.value = false; editingTarget.value = null; form.password = ''; formError.value = '' }
async function create() {
  if (busy.value) return
  busy.value = true; formError.value = ''; notice.value = ''
  const target = editingTarget.value
  const email = form.email.trim().toLowerCase() || null
  const selfCredentialChange = target?.id === props.currentUser.id &&
    (form.username.trim().toLowerCase() !== target.username || email !== target.email || !!form.password)
  try {
    const saved = await api<User>(target ? `/admin/administrators/${target.id}` : '/admin/administrators', target ? 'PATCH' : 'POST', {
      name: form.name, username: form.username, email,
      ...(!target || form.password ? { password: form.password } : {}),
    })
    closeForm()
    if (target?.id === props.currentUser.id) emit('updated', saved)
    if (selfCredentialChange) { needsLogin.value = true; return }
    notice.value = target ? 'Administrador actualizado. Si cambiaste su usuario, correo o contraseña, debe iniciar sesión nuevamente.' : 'Administrador creado. Puede iniciar sesión con su propio usuario y contraseña y gestionar todas las empresas. Entrega sus credenciales por un canal privado.'
    await load()
  } catch (cause) { formError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function remove() {
  const target = deleteTarget.value
  if (!target || busy.value) return
  busy.value = true; deleteError.value = ''; notice.value = ''
  try {
    await api(`/admin/administrators/${target.id}`, 'DELETE')
    deleteTarget.value = null
    notice.value = 'Cuenta administradora eliminada del listado y acceso retirado. Su historial de auditoría se conserva.'
    await load()
  } catch (cause) { deleteError.value = messageOf(cause) }
  finally { busy.value = false }
}
async function changeStatus() {
  const target = statusTarget.value
  if (!target || busy.value) return
  busy.value = true; statusError.value = ''; notice.value = ''
  try {
    await api<User>(`/admin/administrators/${target.id}/status`, 'PATCH', { status: target.status === 'active' ? 'disabled' : 'active' })
    statusTarget.value = null
    notice.value = target.status === 'active' ? 'Administrador desactivado. Sus sesiones anteriores dejaron de ser válidas.' : 'Administrador activado. Debe iniciar sesión nuevamente.'
    await load()
  } catch (cause) { statusError.value = messageOf(cause) }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-heading"><div><h1>Administradores</h1><p class="muted">Crea cuentas de administración para las personas que gestionan la plataforma.</p></div></div>
  <div class="stats-grid"><div class="stat-card"><span>Administradores<AppIcon name="shield" :size="19" /></span><strong>{{ administrators.length }}</strong></div><div class="stat-card"><span>Activos<AppIcon name="check" :size="19" /></span><strong class="metric-success">{{ activeCount }}</strong></div><div class="stat-card"><span>Desactivados<AppIcon name="warning" :size="19" /></span><strong class="metric-danger">{{ administrators.length - activeCount }}</strong></div></div>
  <p class="notice">Todas estas cuentas tienen el mismo rol de administrador y pueden gestionar empresas, clientes, buzones y otros administradores. Los clientes utilizan sus propias cuentas para conectar ChatGPT.</p>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <section class="card management-panel">
    <div class="panel-context"><div><span class="context-label">Administración de plataforma</span><h2>Cuentas administradoras</h2></div><button type="button" class="button secondary small" :disabled="loading || busy" @click="load"><AppIcon name="refresh" :size="16" />Actualizar</button></div>
    <div class="table-toolbar"><label class="filter-search"><span class="sr-only">Buscar administrador</span><AppIcon name="search" :size="19" /><input v-model="query" type="search" maxlength="200" placeholder="Buscar nombre, usuario o correo" /></label><label class="filter-select"><span class="sr-only">Filtrar por estado</span><select v-model="stateFilter"><option value="">Todos los estados</option><option value="active">Activos</option><option value="disabled">Desactivados</option></select></label><button type="button" class="button primary" :disabled="busy" @click="openForm()"><AppIcon name="plus" :size="18" />Crear administrador</button></div>
    <div v-if="loading" class="empty-state" role="status">Cargando administradores…</div>
    <div v-else-if="!filtered.length" class="empty-state"><h3>No se encontraron administradores</h3><p>Prueba con otro nombre, usuario o estado.</p></div>
    <div v-else class="table-scroll"><table><thead><tr><th>Nombre</th><th>Usuario</th><th>Correo</th><th>Estado</th><th>Acciones</th></tr></thead><tbody><tr v-for="user in filtered" :key="user.id"><td><strong>{{ user.name }}</strong><small v-if="user.id === currentUser.id" class="muted"> · Tu cuenta</small></td><td>{{ user.username || 'Acceso por correo' }}</td><td>{{ user.email || 'Sin correo' }}</td><td><span class="badge" :class="user.status">{{ user.status === 'active' ? 'Activo' : 'Desactivado' }}</span></td><td><div class="row-actions"><button type="button" class="button secondary small" :disabled="busy" @click="openForm(user)">Editar</button><button type="button" class="button secondary small" :disabled="busy || user.id === currentUser.id" :title="user.id === currentUser.id ? 'Otro administrador puede desactivar tu cuenta desde su sesión.' : undefined" @click="statusTarget = user; statusError = ''">{{ user.status === 'active' ? 'Desactivar' : 'Activar' }}</button><button type="button" class="button secondary small" :disabled="busy || user.id === currentUser.id" :title="user.id === currentUser.id ? 'No puedes eliminar tu propia cuenta.' : undefined" @click="deleteTarget = user; deleteError = ''">Eliminar</button></div></td></tr></tbody></table></div>
    <div class="panel-bottom"><span>{{ filtered.length }} de {{ administrators.length }} administradores</span><span>Solo se eliminan cuentas desactivadas. Debe quedar un administrador activo.</span></div>
  </section>
  <AppModal :open="showForm" :title="editingTarget ? 'Editar administrador' : 'Crear administrador'" :busy="busy" @close="closeForm">
    <p v-if="formError" class="notice error" role="alert">{{ formError }}</p>
    <form id="administrator-form" @submit.prevent="create"><div class="form-grid">
      <label>Nombre completo<input v-model="form.name" required maxlength="120" placeholder="Persona de ejemplo" autocomplete="off" :disabled="busy" /></label>
      <label>Usuario<input v-model="form.username" required minlength="3" maxlength="32" pattern="[a-zA-Z][a-zA-Z0-9_.\-]{2,31}" placeholder="admin02" autocomplete="off" :disabled="busy" /></label>
      <label>Correo opcional<input v-model="form.email" type="email" maxlength="320" placeholder="administracion@example.com" autocomplete="off" :disabled="busy" /></label>
      <label>{{ editingTarget ? 'Nueva contraseña de Corporate Mail AI' : 'Contraseña de Corporate Mail AI' }}<PasswordInput v-model="form.password" :required="!editingTarget" minlength="6" maxlength="1024" autocomplete="new-password" :placeholder="editingTarget ? 'Vacía para conservar la contraseña actual' : 'Crea una contraseña de al menos 6 caracteres'" :disabled="busy" /></label>
    </div></form>
    <template #footer><button type="button" class="button secondary" :disabled="busy" @click="closeForm">Cancelar</button><button type="submit" form="administrator-form" class="button primary" :disabled="busy">{{ busy ? 'Guardando…' : editingTarget ? 'Guardar cambios' : 'Crear administrador' }}</button></template>
  </AppModal>
  <ConfirmModal :open="!!statusTarget" :title="statusTarget?.status === 'active' ? 'Desactivar administrador' : 'Activar administrador'" :message="statusTarget?.status === 'active' ? 'Esta persona dejará de acceder al panel y sus sesiones anteriores quedarán invalidadas.' : 'Esta persona podrá iniciar sesión nuevamente y gestionar toda la plataforma.'" :confirm-label="statusTarget?.status === 'active' ? 'Desactivar' : 'Activar'" :busy="busy" :error="statusError" @close="statusTarget = null" @confirm="changeStatus" />
  <ConfirmModal :open="!!deleteTarget" title="Eliminar administrador" :message="deleteTarget?.status === 'active' ? 'Esta cuenta está activa. Primero debes desactivarla para poder eliminarla.' : 'La cuenta se retirará del listado y perderá el acceso. Se conservarán su historial de auditoría y los datos de las empresas.'" confirm-label="Eliminar" danger :busy="busy" :error="deleteError" @close="deleteTarget = null" @confirm="remove" />
  <AppModal :open="needsLogin" title="Tu acceso fue actualizado" description="Los cambios se guardaron correctamente." size="small" @close="emit('logout')"><p>Vuelve a iniciar sesión con tu usuario o correo y tu contraseña actualizados.</p><template #footer><button type="button" class="button primary" @click="emit('logout')">Ir a iniciar sesión</button></template></AppModal>
</template>
