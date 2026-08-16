<script setup>
import { reactive, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  folderKey: { type: String, required: true },
  relPath: { type: String, required: true },
})
const emit = defineEmits(['close', 'applied'])

const FIELD_LABELS = {
  title: 'Title', description: 'Description', rights: 'Rights',
  agent: 'People', subject: 'Subjects', date: 'Date', location: 'Location',
}

const file = ref(null)
const comparing = ref(false)
const compareError = ref('')
const result = ref(null) // {measurements, fields, iptc_available}
const selected = reactive({}) // {fieldName: boolean}

const applying = ref(false)
const applyError = ref('')

function onFileChange(event) {
  const chosen = event.target.files[0]
  if (!chosen) return
  file.value = chosen
  compare()
}

async function compare() {
  compareError.value = ''
  result.value = null
  comparing.value = true
  try {
    const data = await api.compareMedia(props.folderKey, props.relPath, file.value)
    result.value = data
    for (const key of Object.keys(selected)) delete selected[key]
    for (const [name, info] of Object.entries(data.fields)) {
      // Pre-checked for fill_record (nothing to lose), left unchecked
      // for conflict (an existing record value would be overwritten --
      // matching desktop's own "Leave as-is" default on a conflict row).
      selected[name] = info.status === 'fill_record'
    }
  } catch (e) {
    compareError.value = e.message || 'Could not read this file'
  } finally {
    comparing.value = false
  }
}

function isActionable(status) {
  return status === 'fill_record' || status === 'conflict'
}

async function onApply() {
  applyError.value = ''
  applying.value = true
  try {
    const selections = {}
    for (const [name, isSelected] of Object.entries(selected)) {
      if (isSelected) selections[name] = 'record'
    }
    const data = await api.applyMedia(props.folderKey, props.relPath, file.value, selections)
    emit('applied', data.record)
  } catch (e) {
    applyError.value = e.message || 'Could not apply media sync'
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>Sync with image file</h2>
        <button class="icon-button" title="Close" @click="emit('close')">✕</button>
      </div>

      <p class="hint">
        Compares this record's fields against the file's own embedded metadata. Only filling the
        record from the file is supported here -- the file itself is never modified.
      </p>

      <input type="file" accept="image/*,.tif,.tiff" @change="onFileChange" />

      <p v-if="comparing">Reading file…</p>
      <p v-if="compareError" class="error">{{ compareError }}</p>

      <template v-if="result">
        <p v-if="!result.iptc_available" class="warning">
          IPTC metadata isn't available on this server (pyexiv2 isn't installed) -- title,
          description, rights, people, and subjects can't be compared. Date, location, and
          dimensions still work.
        </p>

        <table class="measurements-table">
          <tbody>
            <tr>
              <td>Dimensions</td>
              <td>{{ result.measurements.width }} × {{ result.measurements.height }} px</td>
            </tr>
            <tr v-if="result.measurements.resolution">
              <td>Resolution</td>
              <td>{{ result.measurements.resolution }} dpi</td>
            </tr>
            <tr>
              <td>File size</td>
              <td>{{ result.measurements.file_size }} bytes</td>
            </tr>
          </tbody>
        </table>
        <p class="hint">Measurements are always written from the file when you apply.</p>

        <table class="fields-table">
          <thead>
            <tr>
              <th></th>
              <th>Field</th>
              <th>Record</th>
              <th>File</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(info, name) in result.fields" :key="name">
              <td>
                <input
                  v-if="isActionable(info.status)"
                  type="checkbox"
                  v-model="selected[name]"
                />
              </td>
              <td>{{ FIELD_LABELS[name] }}</td>
              <td class="value-cell">{{ Array.isArray(info.record) ? info.record.join(', ') : info.record }}</td>
              <td class="value-cell">{{ Array.isArray(info.file) ? info.file.join(', ') : info.file }}</td>
              <td class="status-cell">{{ info.status }}</td>
            </tr>
          </tbody>
        </table>

        <p v-if="applyError" class="error">{{ applyError }}</p>
        <div class="modal-actions">
          <button class="secondary" @click="emit('close')">Cancel</button>
          <button class="primary" :disabled="applying" @click="onApply">
            {{ applying ? 'Applying…' : 'Apply to record' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 8vh;
  z-index: 100;
  overflow-y: auto;
}
.modal {
  background: white;
  border-radius: 6px;
  padding: 20px;
  width: 640px;
  max-width: 92vw;
  margin-bottom: 8vh;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.modal-header h2 {
  font-size: 1.1em;
}
.icon-button {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 1em;
}
.icon-button:hover {
  color: #b3261e;
}
.hint {
  color: #666;
  font-size: 0.85em;
  margin-bottom: 10px;
}
.warning {
  color: #7a4e00;
  background: #fdecc8;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 0.85em;
  margin: 10px 0;
}
.measurements-table,
.fields-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
  font-size: 0.85em;
}
.measurements-table td,
.fields-table th,
.fields-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #eee;
}
.value-cell {
  color: #444;
  max-width: 160px;
  overflow-wrap: break-word;
}
.status-cell {
  color: #888;
  font-size: 0.9em;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
button.primary,
button.secondary {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  border: none;
}
button.secondary {
  background: #eee;
  color: #333;
}
button.primary {
  background: #2e7d5b;
  color: white;
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
}
</style>
