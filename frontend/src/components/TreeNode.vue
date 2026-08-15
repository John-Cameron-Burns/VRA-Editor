<script setup>
import { inject, reactive, watch } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

// Provided by RecordEditView -- records one field's current edit
// state, keyed by its path, so Save can collect every touched (and
// untouched-but-loaded) leaf's full set of attributes in one pass.
const registerEdit = inject('registerEdit')

const isLeaf = props.node.node_type === 'leaf'

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
</script>

<template>
  <div v-if="node.node_type === 'display'" />

  <div v-else-if="isLeaf" class="field-row">
    <label>{{ friendlyLabel() }}</label>
    <select v-if="node.data.type_choices && node.data.type_choices.length" v-model="field.type">
      <option value="">(none)</option>
      <option v-for="choice in node.data.type_choices" :key="choice" :value="choice">{{ choice }}</option>
    </select>
    <input v-model="field.text" type="text" />
  </div>

  <section v-else-if="node.node_type === 'set' || node.node_type === 'container'" class="node-section" :style="{ marginLeft: depth === 0 ? '0' : '14px' }">
    <h3 v-if="node.label">{{ node.label }}</h3>
    <TreeNode v-for="(child, i) in node.children" :key="i" :node="child" :depth="depth + 1" />
  </section>

  <template v-else>
    <TreeNode v-for="(child, i) in node.children" :key="i" :node="child" :depth="depth" />
  </template>
</template>

<style scoped>
.node-section {
  border-left: 2px solid #e3e3e0;
  padding-left: 12px;
  margin-bottom: 16px;
}
.node-section h3 {
  font-size: 0.95em;
  color: #444;
  margin: 8px 0 6px;
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
</style>
