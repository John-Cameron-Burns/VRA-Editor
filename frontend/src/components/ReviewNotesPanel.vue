<script setup>
import { ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  folderKey: { type: String, required: true },
  relPath: { type: String, required: true },
  notes: { type: Array, required: true },
})

const emit = defineEmits(['update:notes'])

const newNoteText = ref('')
const busy = ref(false)
const error = ref('')

async function addNote() {
  const text = newNoteText.value.trim()
  if (!text) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.addNote(props.folderKey, props.relPath, text)
    emit('update:notes', data.notes)
    newNoteText.value = ''
  } catch (e) {
    error.value = e.message || 'Could not add note'
  } finally {
    busy.value = false
  }
}

async function toggleResolved(index, resolved) {
  busy.value = true
  error.value = ''
  try {
    const data = await api.updateNote(props.folderKey, props.relPath, index, resolved)
    emit('update:notes', data.notes)
  } catch (e) {
    error.value = e.message || 'Could not update note'
  } finally {
    busy.value = false
  }
}

async function removeNote(index) {
  busy.value = true
  error.value = ''
  try {
    const data = await api.deleteNote(props.folderKey, props.relPath, index)
    emit('update:notes', data.notes)
  } catch (e) {
    error.value = e.message || 'Could not remove note'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="review-notes">
    <h2>Review notes</h2>

    <p v-if="notes.length === 0" class="empty">No notes yet.</p>
    <ul v-else class="note-list">
      <li v-for="(note, i) in notes" :key="i" :class="{ resolved: note.resolved }">
        <label class="resolved-check">
          <input type="checkbox" :checked="note.resolved" :disabled="busy" @change="toggleResolved(i, $event.target.checked)" />
        </label>
        <div class="note-body">
          <p class="note-text">{{ note.text }}</p>
          <p class="note-meta">{{ note.author }} · {{ note.date }}</p>
        </div>
        <button class="remove-button" :disabled="busy" @click="removeNote(i)" title="Remove note">✕</button>
      </li>
    </ul>

    <form class="add-note" @submit.prevent="addNote">
      <input v-model="newNoteText" type="text" placeholder="Add a note for the editor…" :disabled="busy" />
      <button type="submit" :disabled="busy || !newNoteText.trim()">Add</button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<style scoped>
.review-notes {
  background: white;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 14px 16px;
  margin-top: 20px;
}
h2 {
  font-size: 1em;
  margin: 0 0 10px;
}
.empty {
  color: #888;
  font-size: 0.9em;
  margin: 0 0 10px;
}
.note-list {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
}
.note-list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.note-list li.resolved .note-text {
  text-decoration: line-through;
  color: #999;
}
.resolved-check {
  padding-top: 2px;
}
.note-body {
  flex: 1;
}
.note-text {
  margin: 0;
}
.note-meta {
  margin: 2px 0 0;
  font-size: 0.8em;
  color: #888;
}
.remove-button {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 0.9em;
}
.remove-button:hover {
  color: #b3261e;
}
.add-note {
  display: flex;
  gap: 8px;
}
.add-note input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.add-note button {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  background: #eee;
  cursor: pointer;
}
.add-note button:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
  margin: 8px 0 0;
}
</style>
