<script setup>
import { onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { api, ApiError } from '../api'
import TreeNode from '../components/TreeNode.vue'
import ReviewNotesPanel from '../components/ReviewNotesPanel.vue'
import { recordActions, clearRecordActions } from '../recordActions'

const props = defineProps({
  folderKey: { type: String, required: true },
  relPath: { type: String, required: true },
})

const router = useRouter()

const tree = ref(null)
const notes = ref([])
const loading = ref(true)
const loadError = ref('')
const saveError = ref('')
const structureError = ref('')
const statusMessage = ref('')
const commitMessage = ref('')
const lockLost = ref(false)
const rejectReason = ref('')
const xmlContent = ref('')
const xmlLoading = ref(false)
const xmlError = ref('')

// Save/Submit/Approve/Reject themselves live in the persistent top bar
// (see App.vue + recordActions.js), not inline on the page -- read/
// write recordActions.saving/submitting/showRejectPrompt directly
// (it's a reactive object, so this works exactly like a local ref)
// rather than keeping a separate copy in sync.

// Bumped every time a structural mutation replaces tree.value, and
// used as part of <TreeNode>'s :key -- forces Vue to fully discard and
// recreate the tree's components rather than reuse them by position,
// since a leaf editor's local field state (in TreeNode.vue) is seeded
// once from its node prop at creation and won't otherwise resync when
// node paths shift after an add/remove.
const treeVersion = ref(0)

const edits = reactive(new Map())
provide('registerEdit', (path, data) => edits.set(JSON.stringify(path), data))

provide('treeActions', {
  addChild: (parentPath, tag) =>
    runStructureAction(() => api.addChild(props.folderKey, props.relPath, parentPath, tag)),
  removeElement: (path) =>
    runStructureAction(() => api.removeElement(props.folderKey, props.relPath, path)),
  setDisplay: (path, translations) =>
    runStructureAction(() => api.setDisplay(props.folderKey, props.relPath, path, translations)),
})

async function runStructureAction(fn) {
  structureError.value = ''
  try {
    // Structural endpoints read the file fresh from disk, not the
    // in-flight edit list -- flush pending field edits first so they
    // aren't silently discarded by the tree-replacing response.
    await flushEdits()
    const data = await fn()
    tree.value = data.record
    edits.clear()
    treeVersion.value += 1
  } catch (e) {
    structureError.value = e.message || 'That change could not be applied'
  }
}

let heartbeatTimer = null
let released = false

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await api.openRecord(props.folderKey, props.relPath)
    tree.value = data.record
    notes.value = data.review_notes
    startHeartbeat(data.heartbeat_interval)
  } catch (e) {
    loadError.value = e.message || 'Could not open this record'
  } finally {
    loading.value = false
  }
}

function startHeartbeat(intervalSeconds) {
  stopHeartbeat()
  heartbeatTimer = setInterval(async () => {
    try {
      await api.heartbeat(props.folderKey, props.relPath)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        lockLost.value = true
        stopHeartbeat()
      }
    }
  }, (intervalSeconds || 30) * 1000)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

async function releaseLock() {
  if (released) return
  released = true
  stopHeartbeat()
  try {
    await api.release(props.folderKey, props.relPath)
  } catch {
    // best-effort -- the lock's TTL expiry covers this if it fails
  }
}

async function flushEdits() {
  // Unvalidated on purpose: this persists pending field edits to the
  // working file right before some other action (Submit/Approve/
  // Reject, or a structural mutation) does its own validated/immediate
  // write -- using the validating Save endpoint here would 422 (and
  // permanently block that other action) whenever the document is
  // currently in one of the momentarily-invalid in-between states
  // structural mutations are allowed to leave it in. See
  // flush_edits's docstring in webapp/routes/record_routes.py.
  await api.flushEdits(props.folderKey, props.relPath, Array.from(edits.values()))
}

async function onSave() {
  saveError.value = ''
  statusMessage.value = ''
  recordActions.saving = true
  try {
    await api.save(props.folderKey, props.relPath, Array.from(edits.values()), commitMessage.value)
    statusMessage.value = 'Saved.'
  } catch (e) {
    saveError.value = e.message || 'Save failed'
  } finally {
    recordActions.saving = false
  }
}

async function onSubmit() {
  saveError.value = ''
  recordActions.submitting = true
  try {
    await flushEdits()
    await api.submit(props.folderKey, props.relPath, commitMessage.value)
    released = true // submit already released it server-side
    router.push({ name: 'folder' })
  } catch (e) {
    saveError.value = e.message || 'Submit failed'
  } finally {
    recordActions.submitting = false
  }
}

async function onApprove() {
  saveError.value = ''
  recordActions.submitting = true
  try {
    await flushEdits()
    await api.approve(props.folderKey, props.relPath, commitMessage.value)
    released = true
    router.push({ name: 'review' })
  } catch (e) {
    saveError.value = e.message || 'Approve failed'
  } finally {
    recordActions.submitting = false
  }
}

async function onReject() {
  saveError.value = ''
  recordActions.submitting = true
  try {
    await flushEdits()
    await api.reject(props.folderKey, props.relPath, rejectReason.value, commitMessage.value)
    released = true
    recordActions.showRejectPrompt = false
    router.push({ name: 'review' })
  } catch (e) {
    saveError.value = e.message || 'Reject failed'
  } finally {
    recordActions.submitting = false
  }
}

async function loadXml() {
  xmlLoading.value = true
  xmlError.value = ''
  try {
    const data = await api.fetchXml(props.folderKey, props.relPath, Array.from(edits.values()))
    xmlContent.value = data.xml
  } catch (e) {
    xmlError.value = e.message || 'Could not load the XML for this record'
  } finally {
    xmlLoading.value = false
  }
}

// The XML panel reflects in-progress edits (see api.fetchXml, which
// flushes them server-side same as flushEdits does), so re-fetch each
// time the top bar's Show XML toggle is switched on rather than
// caching it stale from the first toggle.
watch(
  () => recordActions.showXml,
  (shown) => {
    if (shown) loadXml()
  },
)

recordActions.folderKey = props.folderKey
recordActions.relPath = props.relPath
recordActions.onSave = onSave
recordActions.onSubmit = onSubmit
recordActions.onApprove = onApprove
recordActions.onReject = onReject
recordActions.active = true

onMounted(load)
onBeforeUnmount(() => {
  releaseLock()
  clearRecordActions()
})
onBeforeRouteLeave(async () => {
  await releaseLock()
  return true
})
</script>

<template>
  <div class="record-edit-view">
    <RouterLink :to="folderKey === 'pending' ? '/review' : '/'" class="back-link">
      &larr; Back to {{ folderKey === 'pending' ? 'review queue' : 'edit folder' }}
    </RouterLink>

    <p v-if="loading">Loading…</p>
    <p v-else-if="loadError" class="error">{{ loadError }}</p>

    <template v-else>
      <p v-if="lockLost" class="warning">
        This record's lock was lost -- someone else may now hold it. Saving may fail.
      </p>

      <div class="record-body" :class="{ 'with-xml': recordActions.showXml }">
        <div class="tree-pane">
          <p v-if="structureError" class="error">{{ structureError }}</p>
          <TreeNode :key="treeVersion" :node="tree" />
        </div>

        <div v-if="recordActions.showXml" class="xml-pane">
          <p v-if="xmlLoading">Loading XML…</p>
          <p v-else-if="xmlError" class="error">{{ xmlError }}</p>
          <pre v-else class="xml-content">{{ xmlContent }}</pre>
        </div>
      </div>

      <ReviewNotesPanel :folder-key="folderKey" :rel-path="relPath" :notes="notes" @update:notes="notes = $event" />

      <!-- Save/Submit/Approve/Reject themselves are in the persistent
           top bar (see App.vue) -- this stays for the details that
           belong with the page content: the commit message, status/
           error feedback, and (once Reject is clicked up there) the
           reason prompt. -->
      <div class="save-bar">
        <label class="commit-label">
          Commit message (optional)
          <input v-model="commitMessage" type="text" placeholder="Describe this change" />
        </label>

        <div v-if="recordActions.showRejectPrompt" class="reject-prompt">
          <label>
            Reason for rejecting (optional, becomes a review note)
            <input v-model="rejectReason" type="text" placeholder="What needs to change?" />
          </label>
          <div class="reject-prompt-actions">
            <button class="secondary" @click="recordActions.showRejectPrompt = false">Cancel</button>
            <button class="reject" :disabled="recordActions.submitting" @click="onReject">
              {{ recordActions.submitting ? 'Rejecting…' : 'Confirm reject' }}
            </button>
          </div>
        </div>

        <span v-if="statusMessage" class="status">{{ statusMessage }}</span>
        <p v-if="saveError" class="error">{{ saveError }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 16px;
  color: #555;
  font-size: 0.85em;
}
.save-bar {
  position: sticky;
  bottom: 0;
  background: white;
  border-top: 1px solid #ddd;
  padding: 12px 0;
  margin-top: 20px;
}
.commit-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: #555;
  margin-bottom: 10px;
}
.commit-label input {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.status {
  color: #2e7d5b;
  font-size: 0.85em;
}
button {
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
button.secondary:hover:not(:disabled) {
  background: #ddd;
}
button.reject {
  background: white;
  color: #b3261e;
  border: 1px solid #b3261e;
}
button.reject:hover:not(:disabled) {
  background: #fbeae9;
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #b3261e;
}
.warning {
  color: #7a4e00;
  background: #fdecc8;
  padding: 8px 12px;
  border-radius: 4px;
}
.record-body {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}
.tree-pane {
  flex: 1 1 0;
  min-width: 0;
}
.record-body.with-xml .tree-pane,
.record-body.with-xml .xml-pane {
  flex: 1 1 50%;
}
.xml-pane {
  min-width: 0;
  position: sticky;
  top: 76px;
}
.xml-content {
  background: #2e2e2e;
  color: #e0e0e0;
  padding: 12px 16px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.8em;
  line-height: 1.4;
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}
.reject-prompt {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.reject-prompt label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: #555;
}
.reject-prompt input {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.reject-prompt-actions {
  display: flex;
  gap: 10px;
}
</style>
