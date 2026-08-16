<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()

const revisions = ref([])
const loading = ref(true)
const error = ref('')

const restoringSha = ref('') // which row's restore-prompt is open (sha+filename, since sha alone can touch multiple files)
const destRelPath = ref('')
const restoreBusy = ref(false)
const restoreError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.listAudits(200)
    revisions.value = data.revisions
  } catch (e) {
    error.value = e.message || 'Could not load revision history'
  } finally {
    loading.value = false
  }
}

function basename(filename) {
  return filename.includes('/') ? filename.slice(filename.lastIndexOf('/') + 1) : filename
}

function rowKey(rev) {
  return `${rev.sha}:${rev.filename}`
}

function openRestore(rev) {
  restoreError.value = ''
  restoringSha.value = rowKey(rev)
  destRelPath.value = basename(rev.filename)
}

function cancelRestore() {
  restoringSha.value = ''
}

async function confirmRestore(rev) {
  restoreError.value = ''
  restoreBusy.value = true
  try {
    const data = await api.restoreAudit(rev.sha, rev.filename, destRelPath.value.trim())
    router.push({ name: 'record', params: { folderKey: 'edit', relPath: data.rel_path } })
  } catch (e) {
    restoreError.value = e.message || 'Could not restore this revision'
  } finally {
    restoreBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="audits-view">
    <div class="header-row">
      <h1>Revision history</h1>
      <button class="link-button" @click="load" :disabled="loading">Refresh</button>
    </div>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <p v-else-if="revisions.length === 0" class="empty">No revisions yet.</p>

    <table v-else class="audit-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>File</th>
          <th>Author</th>
          <th>Message</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="rev in revisions" :key="rowKey(rev)">
          <tr>
            <td class="date-cell">{{ new Date(rev.date).toLocaleString() }}</td>
            <td class="filename-cell">{{ rev.filename }}</td>
            <td>{{ rev.author }}</td>
            <td>{{ rev.message }}</td>
            <td>
              <button class="link-button" @click="openRestore(rev)">Restore…</button>
            </td>
          </tr>
          <tr v-if="restoringSha === rowKey(rev)" class="restore-row">
            <td colspan="5">
              <div class="restore-prompt">
                <label>
                  Restore into edit/ as
                  <input v-model="destRelPath" type="text" />
                </label>
                <button class="secondary small" @click="cancelRestore">Cancel</button>
                <button class="primary small" :disabled="restoreBusy || !destRelPath.trim()" @click="confirmRestore(rev)">
                  {{ restoreBusy ? 'Restoring…' : 'Confirm restore' }}
                </button>
                <p v-if="restoreError" class="error">{{ restoreError }}</p>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
h1 {
  font-size: 1.2em;
}
.link-button {
  background: none;
  border: 1px solid #ccc;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
  color: #333;
}
.link-button:disabled {
  opacity: 0.6;
  cursor: default;
}
.audit-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  font-size: 0.9em;
}
.audit-table th,
.audit-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid #eee;
  vertical-align: top;
}
.date-cell {
  white-space: nowrap;
  color: #666;
  font-size: 0.9em;
}
.filename-cell {
  font-family: monospace;
  font-size: 0.85em;
}
.restore-row td {
  background: #f7f7f5;
}
.restore-prompt {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.restore-prompt label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85em;
  color: #555;
}
.restore-prompt input {
  padding: 5px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button.secondary.small,
button.primary.small {
  padding: 4px 10px;
  font-size: 0.85em;
  border-radius: 4px;
  border: none;
  cursor: pointer;
}
button.secondary.small {
  background: #eee;
  color: #333;
}
button.primary.small {
  background: #2e7d5b;
  color: white;
}
button.primary.small:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
  width: 100%;
}
.empty {
  color: #666;
}
</style>
