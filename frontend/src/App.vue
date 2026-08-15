<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { session, logout } from './session'

const router = useRouter()

async function onLogout() {
  await logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <header class="top-bar" v-if="session.username">
      <div class="top-bar-left">
        <RouterLink to="/" class="brand">VRA Editor</RouterLink>
        <RouterLink to="/" class="nav-link">Edit folder</RouterLink>
        <RouterLink to="/review" class="nav-link">Review queue</RouterLink>
        <RouterLink to="/import" class="nav-link">Import</RouterLink>
        <RouterLink to="/audits" class="nav-link">History</RouterLink>
      </div>
      <div class="top-bar-right">
        <span class="user">{{ session.username }}</span>
        <button class="link-button" @click="onLogout">Log out</button>
      </div>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: #2e2e2e;
  color: white;
}
.top-bar-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.brand {
  color: white;
  text-decoration: none;
  font-weight: 600;
}
.nav-link {
  color: rgba(255, 255, 255, 0.75);
  text-decoration: none;
  font-size: 0.9em;
}
.nav-link:hover,
.nav-link.router-link-exact-active {
  color: white;
}
.top-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user {
  opacity: 0.85;
  font-size: 0.9em;
}
.link-button {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.4);
  color: white;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.link-button:hover {
  background: rgba(255, 255, 255, 0.1);
}
.content {
  flex: 1;
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
</style>
