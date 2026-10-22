<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { setAccessToken, type AuthResult, type User } from './api'
import AuthView from './components/AuthView.vue'
import DashboardView from './components/DashboardView.vue'
import ConnectView from './components/ConnectView.vue'
import './style.css'
import './admin-theme.css'

const user = ref<User | null>(null)
const authorizationRequest = new URLSearchParams(window.location.search).get('request') || ''
const connecting = window.location.pathname === '/connect'
if (authorizationRequest) window.history.replaceState({}, '', '/connect')
let expiration: number | undefined
function logout() { user.value = null; setAccessToken(null); window.clearTimeout(expiration) }
function authenticated(result: AuthResult) {
  setAccessToken(result.access_token); user.value = result.user
  window.clearTimeout(expiration); expiration = window.setTimeout(logout, result.expires_in * 1000)
}
window.addEventListener('session-expired', logout)
onUnmounted(() => { window.removeEventListener('session-expired', logout); window.clearTimeout(expiration) })
</script>

<template>
  <ConnectView v-if="user && connecting && authorizationRequest" :user="user" :authorization-request="authorizationRequest" @logout="logout" />
  <DashboardView v-else-if="user?.is_platform_admin && !connecting" :key="user.id" :user="user" @logout="logout" />
  <main v-else-if="user" class="connection-layout"><section class="card consent-card"><h1>Tu cuenta está habilitada</h1><p>Inicia la conexión desde ChatGPT para autorizar el acceso a tus buzones. Si la solicitud expiró, vuelve a conectar Corporate Mail AI desde ChatGPT.</p><button class="button secondary" @click="logout">Cerrar sesión</button></section></main>
  <AuthView v-else :connecting="connecting" @authenticated="authenticated" />
</template>
