<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()

const recordType = ref('work')
const recordId = ref('')
const error = ref('')
const creating = ref(false)

async function onCreate() {
  error.value = ''
  creating.value = true
  try {
    const data = await api.createRecord(recordType.value, recordId.value.trim())
    router.push({ name: 'record', params: { folderKey: 'edit', relPath: data.rel_path } })
  } catch (e) {
    error.value = e.message || 'Could not create this record'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="create-record-view">
    <RouterLink to="/" class="back-link">&larr; Back to edit folder</RouterLink>

    <h1>Create record</h1>

    <form class="create-form" @submit.prevent="onCreate">
      <label>
        Record type
        <select v-model="recordType">
          <option value="work">Work</option>
          <option value="image">Image</option>
          <option value="collection">Collection</option>
        </select>
      </label>

      <label>
        Record ID
        <input v-model="recordId" type="text" placeholder="e.g. smith-portrait-001" />
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button class="primary" type="submit" :disabled="creating || !recordId.trim()">
        {{ creating ? 'Creating…' : 'Create' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 16px;
  color: #555;
  font-size: 0.85em;
}
h1 {
  font-size: 1.2em;
  margin-bottom: 16px;
}
.create-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 360px;
}
.create-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: #555;
}
.create-form input,
.create-form select {
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1em;
}
button.primary {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  border: none;
  background: #2e7d5b;
  color: white;
  align-self: flex-start;
}
button.primary:hover:not(:disabled) {
  background: #266449;
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
}
</style>
