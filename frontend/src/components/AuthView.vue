<script setup lang="ts">
import { ref } from 'vue'
import { api, messageOf, type AuthResult } from '../api'
import AppIcon from './AppIcon.vue'
defineProps<{ connecting?: boolean }>()
const emit = defineEmits<{ authenticated: [result: AuthResult] }>()
const identifier = ref(''), password = ref(''), error = ref(''), busy = ref(false)
const showPassword = ref(false)
async function submit() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try {
    const result = await api<AuthResult>('/auth/login', 'POST', { username: identifier.value, password: password.value })
    password.value = ''; showPassword.value = false; emit('authenticated', result)
  } catch (cause) { error.value = messageOf(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <main class="auth-layout">
    <section class="auth-card" aria-labelledby="login-heading">
      <header class="login-header">
        <span class="login-logo" aria-hidden="true">CM</span>
        <h1 id="login-heading">Corporate Mail <span>AI</span></h1>
        <p>{{ connecting ? 'Inicia sesión para autorizar tu conexión con ChatGPT.' : 'Bienvenido. Inicia sesión para continuar.' }}</p>
      </header>
      <form :aria-busy="busy" @submit.prevent="submit">
        <label for="login-identifier">Usuario o correo
          <span class="login-field"><AppIcon name="user" :size="19" /><input id="login-identifier" v-model="identifier" name="username" type="text" required autocomplete="username" autofocus maxlength="320" placeholder="Tu usuario o correo" :disabled="busy" /></span>
        </label>
        <label for="login-password">Contraseña
          <span class="login-field"><AppIcon name="lock" :size="19" /><input id="login-password" v-model="password" name="password" :type="showPassword ? 'text' : 'password'" required maxlength="1024" autocomplete="current-password" placeholder="Tu contraseña" :disabled="busy" /><button type="button" class="password-toggle" :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'" :aria-pressed="showPassword" aria-controls="login-password" :disabled="busy" @click="showPassword = !showPassword"><AppIcon :name="showPassword ? 'eye-off' : 'eye'" :size="20" /></button></span>
        </label>
        <p v-if="error" id="login-error" class="notice error" role="alert">{{ error }}</p>
        <button type="submit" class="button primary login-submit" :disabled="busy"><span>{{ busy ? 'Ingresando…' : 'Ingresar' }}</span><AppIcon v-if="!busy" name="arrow" :size="19" /></button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-layout {
  min-height: 100vh;
  min-height: 100svh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background: #f4f7f8;
}
.auth-card {
  width: min(100%, 460px);
  padding: 40px;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: #fff;
  box-shadow: 0 18px 60px #173c5012;
}
.login-header { text-align: center; margin-bottom: 32px; }
.login-logo {
  display: inline-grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 19px;
  background: var(--teal);
  color: #fff;
  font-size: 1.3rem;
  font-weight: 700;
  letter-spacing: -1px;
  box-shadow: 0 8px 20px #05869721;
}
.login-header h1 { margin: 20px 0 10px; font-size: 1.55rem; letter-spacing: -.6px; }
.login-header h1 span { color: var(--teal); }
.login-header p { margin: 0; color: var(--muted); font-size: .9rem; }
.auth-card form { display: grid; gap: 22px; }
.auth-card label { gap: 9px; font-size: .88rem; }
.login-field { display: block; position: relative; }
.login-field > .app-icon {
  position: absolute;
  left: 15px;
  top: 50%;
  transform: translateY(-50%);
  color: #7890a3;
  pointer-events: none;
}
.login-field input { height: 52px; padding: 13px 46px; font-size: .94rem; }
.password-toggle {
  position: absolute;
  right: 5px;
  top: 4px;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #738a9e;
}
.password-toggle:hover { color: var(--teal); background: #eaf5f6; }
.password-toggle:focus-visible { outline: 2px solid var(--teal); outline-offset: 0; }
.login-submit { width: 100%; min-height: 52px; margin-top: 7px; font-size: .98rem; }
.auth-card .notice { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 480px) {
  .auth-layout { padding: 24px 16px; }
  .auth-card { padding: 32px 24px; border-radius: 18px; }
  .login-header h1 { font-size: 1.4rem; }
}
</style>
