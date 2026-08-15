<script setup>
import { ref } from 'vue'
import { api } from '../api'

const running = ref(false)
const ranOnce = ref(false)
const error = ref('')
const orphans = ref([]) // [{rel_path, busy, error}]

async function onRunImport() {
  error.value = ''
  running.value = true
  try {
    const data = await api.runImport()
    orphans.value = data.orphan_media.map((o) => ({ ...o, busy: false, error: '' }))
    ranOnce.value = true
  } catch (e) {
    error.value = e.message || 'Import failed'
  } finally {
    running.value = false
  }
}

function leave(orphan) {
  orphans.value = orphans.value.filter((o) => o.rel_path !== orphan.rel_path)
}

async function stash(orphan) {
  orphan.error = ''
  orphan.busy = true
  try {
    await api.stashOrphan(orphan.rel_path)
    orphans.value = orphans.value.filter((o) => o.rel_path !== orphan.rel_path)
  } catch (e) {
    orphan.error = e.message || 'Could not stash this file'
    orphan.busy = false
  }
}

async function ignore(orphan) {
  orphan.error = ''
  orphan.busy = true
  try {
    await api.ignoreOrphan(orphan.rel_path)
    orphans.value = orphans.value.filter((o) => o.rel_path !== orphan.rel_path)
  } catch (e) {
    orphan.error = e.message || 'Could not ignore this file'
    orphan.busy = false
  }
}
</script>

<template>
  <div class="import-view">
    <h1>Import</h1>
    <p class="hint">
      Moves records from the ingest folder into the edit folder, merging any that share a record ID.
      This can take a while for a large backlog -- the page will wait for it to finish.
    </p>

    <button class="primary" :disabled="running" @click="onRunImport">
      {{ running ? 'Importing…' : 'Run Import' }}
    </button>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="ranOnce && !running">
      <p v-if="orphans.length === 0" class="status">Import complete. No leftover media to review.</p>
      <template v-else>
        <h2>Leftover media</h2>
        <p class="hint">
          These files have no matching record and were left in the ingest folder. Choose what to do
          with each one.
        </p>
        <table class="orphan-table">
          <thead>
            <tr>
              <th>File</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="orphan in orphans" :key="orphan.rel_path">
              <td>
                {{ orphan.rel_path }}
                <p v-if="orphan.error" class="error">{{ orphan.error }}</p>
              </td>
              <td class="actions">
                <button class="secondary small" :disabled="orphan.busy" @click="leave(orphan)">Leave</button>
                <button class="secondary small" :disabled="orphan.busy" @click="stash(orphan)">Stash</button>
                <button class="secondary small" :disabled="orphan.busy" @click="ignore(orphan)">
                  Ignore
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>

<style scoped>
h1 {
  font-size: 1.2em;
  margin-bottom: 8px;
}
h2 {
  font-size: 1em;
  margin: 20px 0 6px;
}
.hint {
  color: #666;
  font-size: 0.85em;
  margin-bottom: 14px;
}
button.primary {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  border: none;
  background: #2e7d5b;
  color: white;
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.status {
  color: #2e7d5b;
  margin-top: 14px;
}
.orphan-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  margin-top: 8px;
}
.orphan-table th,
.orphan-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid #eee;
  font-size: 0.9em;
}
.actions {
  display: flex;
  gap: 6px;
  white-space: nowrap;
}
button.secondary.small {
  padding: 4px 10px;
  font-size: 0.85em;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  background: #eee;
  color: #333;
}
button.secondary.small:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
  margin-top: 14px;
}
</style>
