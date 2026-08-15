<script setup>
import { computed, inject, reactive, ref, watch } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

// Provided by RecordEditView -- records one field's current edit
// state, keyed by its path, so Save can collect every touched (and
// untouched-but-loaded) leaf's full set of attributes in one pass.
const registerEdit = inject('registerEdit')
// addChild/removeElement/setDisplay -- each an immediate-apply action
// (see webapp/routes/structure_routes.py), not staged like field edits.
const treeActions = inject('treeActions')

const isLeaf = props.node.node_type === 'leaf'
const isRoot = props.node.node_type === 'record'
const isBranch = props.node.node_type === 'set' || props.node.node_type === 'container'

// Seeded from the field's current value/attributes so a save that
// only touches text doesn't silently blank out vocab/refid/href/lang
// -- set_element_data on the backend writes back exactly what's sent,
// there's no partial-update merge on its side.
const field = isLeaf
  ? reactive({
      text: props.node.data.text || '',
      vocab: props.node.data.vocab || '',
      refid: props.node.data.refid || '',
      href: props.node.data.href || '',
      lang: props.node.data.lang || '',
      type: props.node.data.type || '',
    })
  : null

if (isLeaf) {
  watch(
    field,
    (value) => registerEdit(props.node.path, { path: props.node.path, ...value }),
    { immediate: true, deep: true },
  )
}

function friendlyLabel() {
  // node.label already comes pre-formatted from the backend
  // (e.g. "Title: My Painting" for a filled leaf, "Title" for an
  // empty one) -- strip the ": value" part here since the input
  // itself shows the value.
  const idx = props.node.label.indexOf(':')
  return isLeaf && idx !== -1 ? props.node.label.slice(0, idx) : props.node.label
}

// --- add/remove child (record/set/container nodes) ---

const addableSpecs = computed(() => {
  if (!(isRoot || isBranch)) return []
  return (props.node.child_specs || [])
    .filter((spec) => spec.tag !== 'display') // display gets its own dedicated editor below, not the generic add-list
    .filter((spec) => {
      if (spec.max_occurs === null) return true
      const count = props.node.children.filter((c) => c.data.tag === spec.tag).length
      return count < spec.max_occurs
    })
})
const selectedAddTag = ref('')
const addBusy = ref(false)

async function onAddChild() {
  if (!selectedAddTag.value) return
  addBusy.value = true
  try {
    await treeActions.addChild(props.node.path, selectedAddTag.value)
    selectedAddTag.value = ''
  } finally {
    addBusy.value = false
  }
}

const removeBusy = ref(false)

async function onRemove() {
  removeBusy.value = true
  try {
    await treeActions.removeElement(props.node.path)
  } finally {
    removeBusy.value = false
  }
}

// --- display translations (record/set/container nodes only; not
// every node supports it -- only ones whose schema declares a
// `display` child, surfaced the same way any other addable child is) ---

const displayChild = computed(() => props.node.children.find((c) => c.node_type === 'display'))
const supportsDisplay = computed(() =>
  (isRoot || isBranch) && (props.node.child_specs || []).some((spec) => spec.tag === 'display'),
)
// Children actually rendered as their own rows -- the display child
// (if any) gets its own editor below instead of a generic recursive row.
const visibleChildren = computed(() => props.node.children.filter((c) => c.node_type !== 'display'))

const showDisplayEditor = ref(false)
const displayRows = reactive([])
const displayBusy = ref(false)
const displayError = ref('')

function openDisplayEditor() {
  displayRows.splice(0, displayRows.length)
  const translations = displayChild.value ? displayChild.value.data.translations : {}
  for (const [lang, text] of Object.entries(translations)) {
    displayRows.push({ lang, text })
  }
  if (displayRows.length === 0) displayRows.push({ lang: '', text: '' })
  showDisplayEditor.value = true
}

function addDisplayRow() {
  displayRows.push({ lang: '', text: '' })
}

function removeDisplayRow(i) {
  displayRows.splice(i, 1)
}

async function saveDisplayRows() {
  displayError.value = ''
  displayBusy.value = true
  try {
    const translations = {}
    for (const row of displayRows) {
      if (row.lang.trim()) translations[row.lang.trim()] = row.text
    }
    const path = displayChild.value ? displayChild.value.path : props.node.path
    await treeActions.setDisplay(path, translations)
    showDisplayEditor.value = false
  } catch (e) {
    displayError.value = e.message || 'Could not save translations'
  } finally {
    displayBusy.value = false
  }
}
</script>

<template>
  <div v-if="isLeaf" class="field-row">
    <label>{{ friendlyLabel() }}</label>
    <select v-if="node.data.type_choices && node.data.type_choices.length" v-model="field.type">
      <option value="">(none)</option>
      <option v-for="choice in node.data.type_choices" :key="choice" :value="choice">{{ choice }}</option>
    </select>
    <input v-model="field.text" type="text" />
    <button class="icon-button" :disabled="removeBusy" title="Remove" @click="onRemove">✕</button>
  </div>

  <section v-else-if="isBranch || isRoot" class="node-section" :style="{ marginLeft: depth === 0 ? '0' : '14px' }">
    <div v-if="node.label" class="section-header">
      <h3>{{ node.label }}</h3>
      <div class="section-header-actions">
        <button v-if="supportsDisplay" class="icon-button" title="Language translations" @click="openDisplayEditor">🌐</button>
        <button v-if="!isRoot" class="icon-button" :disabled="removeBusy" title="Remove" @click="onRemove">✕</button>
      </div>
    </div>

    <div v-if="showDisplayEditor" class="display-editor">
      <div v-for="(row, i) in displayRows" :key="i" class="display-row">
        <input v-model="row.lang" type="text" placeholder="lang (e.g. en)" class="display-lang" />
        <input v-model="row.text" type="text" placeholder="Text" />
        <button class="icon-button" @click="removeDisplayRow(i)">✕</button>
      </div>
      <div class="display-editor-actions">
        <button class="secondary small" @click="addDisplayRow">+ Add language</button>
        <button class="secondary small" @click="showDisplayEditor = false">Cancel</button>
        <button class="primary small" :disabled="displayBusy" @click="saveDisplayRows">
          {{ displayBusy ? 'Saving…' : 'Save translations' }}
        </button>
      </div>
      <p v-if="displayError" class="error">{{ displayError }}</p>
    </div>

    <TreeNode v-for="(child, i) in visibleChildren" :key="i" :node="child" :depth="depth + 1" />

    <div v-if="addableSpecs.length" class="add-row">
      <select v-model="selectedAddTag">
        <option value="">+ Add…</option>
        <option v-for="spec in addableSpecs" :key="spec.tag" :value="spec.tag">{{ spec.label }}</option>
      </select>
      <button class="secondary small" :disabled="!selectedAddTag || addBusy" @click="onAddChild">
        {{ addBusy ? 'Adding…' : 'Add' }}
      </button>
    </div>
  </section>

  <template v-else>
    <TreeNode v-for="(child, i) in visibleChildren" :key="i" :node="child" :depth="depth" />
  </template>
</template>

<style scoped>
.node-section {
  border-left: 2px solid #e3e3e0;
  padding-left: 12px;
  margin-bottom: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-header h3 {
  font-size: 0.95em;
  color: #444;
  margin: 8px 0 6px;
}
.section-header-actions {
  display: flex;
  gap: 4px;
}
.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.field-row label {
  flex: 0 0 140px;
  font-size: 0.85em;
  color: #555;
}
.field-row input[type='text'] {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.field-row select {
  padding: 5px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.icon-button {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 0.9em;
  padding: 2px 6px;
}
.icon-button:hover:not(:disabled) {
  color: #b3261e;
}
.icon-button:disabled {
  opacity: 0.5;
  cursor: default;
}
.add-row {
  display: flex;
  gap: 8px;
  margin: 8px 0;
}
.add-row select {
  padding: 5px;
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
button.secondary.small:disabled,
button.primary.small:disabled {
  opacity: 0.6;
  cursor: default;
}
.display-editor {
  background: #f7f7f5;
  border: 1px solid #e3e3e0;
  border-radius: 4px;
  padding: 10px;
  margin: 8px 0;
}
.display-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.display-row input {
  padding: 5px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.display-lang {
  flex: 0 0 100px;
}
.display-row input:not(.display-lang) {
  flex: 1;
}
.display-editor-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.error {
  color: #b3261e;
  font-size: 0.85em;
}
</style>
