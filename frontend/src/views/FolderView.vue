<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  folderKey: { type: String, default: 'edit' },
})

const records = ref([])
const loading = ref(true)
const error = ref('')

const title = computed(() => (props.folderKey === 'pending' ? 'Review queue' : 'Edit folder'))
const emptyMessage = computed(() =>
  props.folderKey === 'pending' ? 'No records awaiting review.' : 'No records in the edit folder.',
)

// Edit folder merges 'edit' and 'rejected' records into one list (see
// webapp/records_common.py's FOLDER_SOURCES) -- each record's status
// says which one it's actually sitting in, since a rejected record is
// opened/saved/resubmitted exactly the same way as an editable one.
const STATUS_LABELS = { edit: 'Editable', rejected: 'Rejected', pending: 'Pending' }
function statusLabel(status) {
  return STATUS_LABELS[status] || status
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.listFolder(props.folderKey)
    records.value = data.records
  } catch (e) {
    error.value = e.message || 'Could not load records'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.folderKey, load)
</script>

<template>
  <div class="folder-view">
    <div class="header-row">
      <h1>{{ title }}</h1>
      <div class="header-actions">
        <RouterLink v-if="folderKey === 'edit'" to="/create" class="link-button">+ Create record</RouterLink>
        <button class="link-button" @click="load" :disabled="loading">Refresh</button>
      </div>
    </div>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <p v-else-if="records.length === 0" class="empty">{{ emptyMessage }}</p>

    <table v-else class="record-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Path</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="rec in records" :key="rec.rel_path">
          <td>
            <RouterLink v-if="!rec.locked_by" :to="`/records/${folderKey}/${rec.rel_path}`">{{ rec.title }}</RouterLink>
            <span v-else class="locked-title">{{ rec.title }}</span>
          </td>
          <td class="rel-path">{{ rec.rel_path }}</td>
          <td>
            <span class="status-badge" :class="rec.status">{{ statusLabel(rec.status) }}</span>
            <span v-if="rec.locked_by" class="lock-badge">Locked by {{ rec.locked_by }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h1 {
  font-size: 1.2em;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.link-button {
  background: none;
  border: 1px solid #ccc;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
  color: #333;
  text-decoration: none;
}
.record-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
  background: white;
}
.record-table th,
.record-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid #eee;
}
.rel-path {
  color: #888;
  font-size: 0.85em;
}
.locked-title {
  color: #888;
}
.lock-badge {
  background: #fdecc8;
  color: #7a4e00;
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 6px;
}
.status-badge {
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 10px;
}
.status-badge.edit {
  background: #e3f2e9;
  color: #2e7d5b;
}
.status-badge.rejected {
  background: #fbeae9;
  color: #b3261e;
}
.status-badge.pending {
  background: #eee;
  color: #555;
}
.error {
  color: #b3261e;
}
.empty {
  color: #666;
}
</style>
