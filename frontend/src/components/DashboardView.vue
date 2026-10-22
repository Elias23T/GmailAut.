<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, messageOf, type Tenant, type User } from '../api'
import MailboxesView from './MailboxesView.vue'
import ClientsView from './ClientsView.vue'
import CompaniesView from './CompaniesView.vue'
import AppModal from './AppModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ user: User }>()
const emit = defineEmits<{ logout: [] }>()
const tenants = ref<Tenant[]>([]), selectedId = ref(''), tab = ref('mailboxes')
const loading = ref(true), error = ref(''), closingSession = ref(false)
const collapsed = ref(false), mobileMenuOpen = ref(false), helpOpen = ref(false), profileOpen = ref(false)
const mobileQuery = window.matchMedia('(max-width: 900px)')
const isMobile = ref(mobileQuery.matches)
const menuButton = ref<HTMLButtonElement | null>(null)
watch(mobileMenuOpen, async open => {
  await nextTick()
  if (!isMobile.value) return
  if (open) document.querySelector<HTMLButtonElement>('#main-sidebar nav button')?.focus()
  else menuButton.value?.focus()
})
const sectionNames: Record<string, string> = { mailboxes: 'Buzones corporativos', companies: 'Empresas', clients: 'Clientes y accesos' }
const sectionName = computed(() => sectionNames[tab.value] || 'Administración')
const initials = computed(() => props.user.name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase())
function updateViewport(event: MediaQueryListEvent) { isMobile.value = event.matches; mobileMenuOpen.value = false }
function toggleMenu() { if (isMobile.value) mobileMenuOpen.value = !mobileMenuOpen.value; else collapsed.value = !collapsed.value }
function navigate(section: string) { tab.value = section; mobileMenuOpen.value = false }
function closeMenu(event: KeyboardEvent) { if (event.key === 'Escape') mobileMenuOpen.value = false }
onMounted(() => { mobileQuery.addEventListener('change', updateViewport); window.addEventListener('keydown', closeMenu) })
onUnmounted(() => { mobileQuery.removeEventListener('change', updateViewport); window.removeEventListener('keydown', closeMenu) })
const activeTenants = computed(() => tenants.value.filter(tenant => tenant.status === 'active'))
const selected = computed(() => activeTenants.value.find(tenant => tenant.id === selectedId.value))
function ensureSelection() {
  if (!activeTenants.value.some(tenant => tenant.id === selectedId.value)) selectedId.value = activeTenants.value[0]?.id || ''
}
function companyUpdated(tenant: Tenant) {
  const index = tenants.value.findIndex(item => item.id === tenant.id)
  if (index < 0) tenants.value.push(tenant)
  else tenants.value[index] = tenant
  ensureSelection()
}
function companyRemoved(id: string) { tenants.value = tenants.value.filter(tenant => tenant.id !== id); ensureSelection() }
function selectCompany(id: string) { selectedId.value = id; navigate('mailboxes') }
async function loadTenants() {
  error.value = ''; loading.value = true
  try {
    tenants.value = await api<Tenant[]>('/tenants')
    ensureSelection()
  } catch (cause) { error.value = messageOf(cause) }
  finally { loading.value = false }
}
onMounted(loadTenants)
</script>

<template>
  <div class="app-layout admin-shell" :class="{ 'sidebar-collapsed': collapsed, 'mobile-menu-open': mobileMenuOpen }">
    <button v-if="mobileMenuOpen" type="button" class="sidebar-overlay" aria-label="Cerrar menú" @click="mobileMenuOpen = false"></button>
    <aside id="main-sidebar" class="sidebar" :inert="isMobile && !mobileMenuOpen">
      <a class="brand sidebar-brand" href="/" @click.prevent="navigate('mailboxes')">
        <span class="brand-mark">CM</span><span class="brand-name">Corporate Mail <b>AI</b></span>
      </a>
      <div class="side-navigation">
        <div class="sidebar-label">ADMINISTRACIÓN</div>
        <nav aria-label="Secciones">
          <button type="button" :class="{ selected: tab === 'mailboxes' }" :aria-current="tab === 'mailboxes' ? 'page' : undefined" title="Buzones" @click="navigate('mailboxes')"><AppIcon name="mail" /><span class="nav-label">Buzones</span></button>
          <button type="button" :class="{ selected: tab === 'companies' }" :aria-current="tab === 'companies' ? 'page' : undefined" title="Empresas" @click="navigate('companies')"><AppIcon name="building" /><span class="nav-label">Empresas</span></button>
          <button type="button" :class="{ selected: tab === 'clients' }" :aria-current="tab === 'clients' ? 'page' : undefined" title="Clientes" @click="navigate('clients')"><AppIcon name="users" /><span class="nav-label">Clientes</span></button>
        </nav>
      </div>
      <div class="sidebar-bottom">
        <div class="read-only"><AppIcon name="shield" :size="22" /><div><strong>Acceso de solo lectura</strong><small>Tus correos permanecen en su proveedor.</small></div></div>
        <button type="button" class="sidebar-logout" title="Cerrar sesión" @click="closingSession = true"><AppIcon name="logout" /><span class="nav-label">Cerrar sesión</span></button>
      </div>
    </aside>
    <main class="workspace" :inert="isMobile && mobileMenuOpen">
      <header class="topbar">
        <div class="topbar-context">
          <button ref="menuButton" type="button" class="header-icon-button menu-toggle" :aria-label="isMobile ? (mobileMenuOpen ? 'Cerrar menú' : 'Abrir menú') : (collapsed ? 'Expandir menú' : 'Contraer menú')" :aria-expanded="isMobile ? mobileMenuOpen : !collapsed" aria-controls="main-sidebar" @click="toggleMenu"><AppIcon name="layout" :size="22" /></button>
          <AppIcon name="shield" :size="22" /><span>Administración de plataforma</span>
        </div>
        <div class="topbar-actions">
          <button type="button" class="guide-button" @click="helpOpen = true"><AppIcon name="help" /><span>Guía</span></button>
          <button type="button" class="header-profile" aria-label="Abrir mi cuenta" @click="profileOpen = true">
            <span class="profile-avatar">{{ initials }}</span><span class="header-profile-info"><strong>{{ user.name }}</strong><small>Administrador del sistema</small></span><AppIcon name="down" :size="15" />
          </button>
        </div>
      </header>
      <div class="page-content">
        <nav class="breadcrumbs" aria-label="Ruta actual"><button type="button" @click="navigate('mailboxes')"><AppIcon name="home" :size="17" />Plataforma</button><span aria-hidden="true">/</span><span aria-current="page">{{ sectionName }}</span></nav>
        <p v-if="error" role="alert" class="notice error">{{ error }} <button class="text-button" @click="loadTenants">Reintentar</button></p>
        <AppModal :open="helpOpen" title="Empieza con Corporate Mail AI" description="Configura el acceso de tus clientes paso a paso." @close="helpOpen = false">
          <ol class="guide-steps"><li><strong>Crea una empresa.</strong><p>Entra en Empresas, crea y selecciona la empresa que deseas administrar.</p></li><li><strong>Conecta y verifica un buzón.</strong><p>Utiliza los datos IMAP y la contraseña que te proporciona el proveedor del correo.</p></li><li><strong>Agrega clientes y autoriza sus buzones.</strong><p>Configura los accesos desde Buzones → Permisos.</p></li><li><strong>Conecta ChatGPT.</strong><p>En Clientes → Conexión ChatGPT encontrarás la URL. Necesitas un dominio HTTPS para conectarla desde ChatGPT.</p></li></ol>
          <template #footer><button type="button" class="button primary" @click="helpOpen = false">Entendido</button></template>
        </AppModal>
        <AppModal :open="profileOpen" title="Mi cuenta" description="Administrador de Corporate Mail AI." size="small" @close="profileOpen = false">
          <div class="account-summary"><span class="profile-avatar large">{{ initials }}</span><div><strong>{{ user.name }}</strong><p class="muted">{{ user.username || user.email }}</p></div></div>
          <p class="notice"><AppIcon name="shield" :size="18" /> Tu cuenta administra empresas, clientes y conexiones de correo.</p>
          <template #footer><button type="button" class="button secondary" @click="profileOpen = false">Cerrar</button><button type="button" class="button primary" @click="profileOpen = false; closingSession = true"><AppIcon name="logout" :size="17" />Cerrar sesión</button></template>
        </AppModal>
        <ConfirmModal :open="closingSession" title="Cerrar sesión" message="Volverás a la pantalla de acceso." confirm-label="Cerrar sesión" @close="closingSession = false" @confirm="emit('logout')" />
        <CompaniesView v-if="tab === 'companies'" :tenants="tenants" :selected-id="selectedId" :loading="loading" @updated="companyUpdated" @removed="companyRemoved" @select="selectCompany" @refresh="loadTenants" />
        <div v-else-if="loading" class="empty-state" role="status">Cargando tu espacio…</div>
        <ClientsView v-else-if="tab === 'clients'" :tenant="selected" :tenants="activeTenants" @select="selectedId = $event" @manage-companies="navigate('companies')" />
        <section v-else-if="!selected" class="empty-state card"><span class="empty-icon"><AppIcon name="building" :size="28" /></span><h1>{{ tenants.length ? 'No hay empresas activas' : 'Crea tu primera empresa' }}</h1><p>En Empresas puedes crear, seleccionar o activar una empresa para administrar sus clientes y buzones.</p><button type="button" class="button primary" @click="navigate('companies')"><AppIcon name="building" :size="18" />Ir a Empresas</button></section>
        <template v-else>
          <div class="workspace-company"><label for="workspace-tenant">Empresa seleccionada<select id="workspace-tenant" v-model="selectedId"><option v-for="tenant in activeTenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option></select></label><button type="button" class="text-button" @click="navigate('companies')">Administrar empresas</button></div>
          <MailboxesView v-if="tab === 'mailboxes'" :key="selected.id" :tenant="selected" />
        </template>
      </div>
    </main>
  </div>
</template>
