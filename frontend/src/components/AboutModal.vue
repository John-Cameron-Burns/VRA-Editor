<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['close'])

const version = ref('')

onMounted(async () => {
  try {
    const data = await api.getVersion()
    version.value = data.version
  } catch {
    version.value = 'unknown'
  }
})
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>About</h2>
        <button class="icon-button" title="Close" @click="emit('close')">✕</button>
      </div>

      <p class="app-name">VRA Core 4 XML Editor -- Web</p>
      <p v-if="version">Version {{ version }}</p>
      <p>Copyright &copy; 2026 John Burns and Impact Data Metrics Limited.</p>
      <p>
        Licensed under the
        <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">
          Creative Commons Attribution-NonCommercial 4.0 International License
        </a>
        (CC BY-NC 4.0).
      </p>
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
  width: 420px;
  max-width: 90vw;
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
.app-name {
  font-weight: 600;
}
.modal p {
  margin: 6px 0;
  font-size: 0.9em;
  color: #444;
}
.modal a {
  color: #2e7d5b;
}
</style>
