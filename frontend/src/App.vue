<script setup>
import { ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { session, logout } from './session'
import { recordActions } from './recordActions'
import AboutModal from './components/AboutModal.vue'

const router = useRouter()
const route = useRoute()
const showAbout = ref(false)

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

      <!-- Record-level actions -- populated by RecordEditView while a
           record is open, matching the desktop app's own toolbar
           placement for Save/Submit/Approve/Reject rather than having
           them live inline with the page content. -->
      <div class="top-bar-record-actions" v-if="recordActions.active">
        <span v-if="recordActions.saving" class="status">Saving…</span>
        <button
          class="secondary"
          :disabled="recordActions.saving || recordActions.submitting"
          @click="recordActions.onSave"
        >
          Save
        </button>
        <template v-if="recordActions.folderKey === 'pending'">
          <button
            class="reject"
            :disabled="recordActions.saving || recordActions.submitting"
            @click="recordActions.showRejectPrompt = true"
          >
            Reject
          </button>
          <button
            class="primary"
            :disabled="recordActions.saving || recordActions.submitting"
            @click="recordActions.onApprove"
          >
            {{ recordActions.submitting ? 'Approving…' : 'Approve' }}
          </button>
        </template>
        <template v-else>
          <button
            class="primary"
            :disabled="recordActions.saving || recordActions.submitting"
            @click="recordActions.onSubmit"
          >
            {{ recordActions.submitting ? 'Submitting…' : 'Submit for review' }}
          </button>
        </template>

        <button
          class="secondary"
          :class="{ active: recordActions.showXml }"
          @click="recordActions.showXml = !recordActions.showXml"
        >
          {{ recordActions.showXml ? 'Hide XML' : 'Show XML' }}
        </button>

        <span class="top-bar-divider"></span>
        <span class="export-label">Export:</span>
        <a
          class="secondary"
          :href="`/api/records/${recordActions.folderKey}/${recordActions.relPath}/export/dublin-core`"
        >
          Dublin Core
        </a>
        <a
          class="secondary"
          :href="`/api/records/${recordActions.folderKey}/${recordActions.relPath}/export/lido`"
        >
          LIDO
        </a>
      </div>

      <div class="top-bar-right">
        <span class="user">{{ session.username }}</span>
        <button class="link-button" @click="showAbout = true">About</button>
        <button class="link-button" @click="onLogout">Log out</button>
      </div>
    </header>
    <main class="content" :class="{ 'content-wide': route.name === 'record' && recordActions.showXml }">
      <RouterView />
    </main>

    <AboutModal v-if="showAbout" @close="showAbout = false" />
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
  position: sticky;
  top: 0;
  z-index: 10;
}
.top-bar-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.top-bar-record-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.top-bar-record-actions .status {
  color: #7fd9ac;
  font-size: 0.85em;
}
.top-bar-record-actions button,
.top-bar-record-actions a {
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85em;
  border: none;
  text-decoration: none;
  display: inline-block;
}
.top-bar-record-actions button.secondary,
.top-bar-record-actions a.secondary {
  background: rgba(255, 255, 255, 0.15);
  color: white;
}
.top-bar-record-actions button.secondary:hover:not(:disabled),
.top-bar-record-actions a.secondary:hover {
  background: rgba(255, 255, 255, 0.25);
}
.top-bar-record-actions button.secondary.active {
  background: rgba(255, 255, 255, 0.35);
}
.top-bar-divider {
  width: 1px;
  align-self: stretch;
  background: rgba(255, 255, 255, 0.2);
  margin: 0 2px;
}
.export-label {
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85em;
}
.top-bar-record-actions button.primary {
  background: #2e7d5b;
  color: white;
}
.top-bar-record-actions button.primary:hover:not(:disabled) {
  background: #359268;
}
.top-bar-record-actions button.reject {
  background: transparent;
  color: #ff8a80;
  border: 1px solid #ff8a80;
}
.top-bar-record-actions button.reject:hover:not(:disabled) {
  background: rgba(255, 138, 128, 0.15);
}
.top-bar-record-actions button:disabled {
  opacity: 0.5;
  cursor: default;
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
.content.content-wide {
  max-width: 1400px;
}
</style>
