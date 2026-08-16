<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  initialQuery: { type: String, default: '' },
})
const emit = defineEmits(['close', 'pick'])

const vocabularies = ref([])
const vocab = ref('')
const query = ref(props.initialQuery)
const results = ref([])
const searching = ref(false)
const error = ref('')
const searched = ref(false)

onMounted(async () => {
  const data = await api.listVocabularies()
  vocabularies.value = data.vocabularies
  vocab.value = data.vocabularies[0]?.key || ''
})

async function onSearch() {
  if (!vocab.value || !query.value.trim()) return
  error.value = ''
  searching.value = true
  searched.value = true
  try {
    const data = await api.searchVocab(vocab.value, query.value.trim())
    results.value = data.results
  } catch (e) {
    error.value = e.message || 'Search failed'
    results.value = []
  } finally {
    searching.value = false
  }
}

function pick(result) {
  emit('pick', result)
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>Search authority</h2>
        <button class="icon-button" title="Close" @click="emit('close')">✕</button>
      </div>

      <form class="search-form" @submit.prevent="onSearch">
        <select v-model="vocab">
          <option v-for="v in vocabularies" :key="v.key" :value="v.key">{{ v.label }}</option>
        </select>
        <input v-model="query" type="text" placeholder="Search term" autofocus />
        <button class="primary" type="submit" :disabled="searching || !query.trim()">
          {{ searching ? 'Searching…' : 'Search' }}
        </button>
      </form>

      <p v-if="error" class="error">{{ error }}</p>

      <ul v-if="results.length" class="results">
        <li v-for="r in results" :key="r.vocab + r.refid" class="result-row" @click="pick(r)">
          <span class="result-label">{{ r.label }}</span>
          <span class="result-refid">{{ r.refid }}</span>
        </li>
      </ul>
      <p v-else-if="searched && !searching" class="empty">No results.</p>
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
  padding-top: 10vh;
  z-index: 100;
}
.modal {
  background: white;
  border-radius: 6px;
  padding: 20px;
  width: 480px;
  max-width: 90vw;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
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
.search-form {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.search-form select {
  flex: 0 0 auto;
  max-width: 160px;
  padding: 6px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.search-form input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button.primary {
  padding: 6px 14px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  background: #2e7d5b;
  color: white;
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.results {
  list-style: none;
  overflow-y: auto;
  border-top: 1px solid #eee;
}
.result-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
}
.result-row:hover {
  background: #f5f5f3;
}
.result-refid {
  color: #888;
  font-size: 0.8em;
  white-space: nowrap;
}
.empty {
  color: #666;
  font-size: 0.9em;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
}
</style>
