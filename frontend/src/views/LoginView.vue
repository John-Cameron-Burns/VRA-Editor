<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../session'

const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

const route = useRoute()
const router = useRouter()

async function onSubmit() {
  error.value = ''
  submitting.value = true
  try {
    await login(username.value.trim(), password.value)
    router.push(route.query.redirect || { name: 'folder' })
  } catch (e) {
    error.value = e.message || 'Login failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <h1>VRA Editor</h1>
      <p class="subtitle">Sign in with your network account</p>

      <label>
        Username
        <input v-model="username" type="text" autocomplete="username" autofocus required />
      </label>
      <label>
        Password
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button type="submit" :disabled="submitting">
        {{ submitting ? 'Signing in…' : 'Sign in' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.login-card {
  background: white;
  padding: 32px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
h1 {
  margin: 0;
  font-size: 1.3em;
}
.subtitle {
  margin: 0 0 6px;
  color: #666;
  font-size: 0.9em;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: #444;
}
input {
  padding: 8px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
  margin: 0;
}
button {
  padding: 10px;
  border: none;
  border-radius: 4px;
  background: #2e7d5b;
  color: white;
  font-weight: 600;
  cursor: pointer;
}
button:disabled {
  background: #a9c3b7;
  cursor: default;
}
button:not(:disabled):hover {
  background: #266449;
}
</style>
