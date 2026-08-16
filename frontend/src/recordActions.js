// Mirrors session.js's pattern: a plain reactive object, not a state
// library, since this is just "what buttons should the persistent top
// bar show right now." RecordEditView populates it while it's the
// active route -- Save/Submit for review/Approve/Reject then render
// in App.vue's top bar (matching the desktop app's own toolbar
// placement for these) instead of inline at the bottom of the page.
// active stays false (top bar shows nothing extra) whenever no record
// is open.

import { reactive } from 'vue'

export const recordActions = reactive({
  active: false,
  folderKey: null, // 'edit' | 'pending' -- which action set to show
  relPath: null, // needed to build the export links' hrefs
  saving: false,
  submitting: false,
  showRejectPrompt: false,
  showXml: false,
  onSave: null,
  onSubmit: null,
  onApprove: null,
  onReject: null,
})

export function clearRecordActions() {
  recordActions.active = false
  recordActions.folderKey = null
  recordActions.relPath = null
  recordActions.saving = false
  recordActions.submitting = false
  recordActions.showRejectPrompt = false
  recordActions.showXml = false
  recordActions.onSave = null
  recordActions.onSubmit = null
  recordActions.onApprove = null
  recordActions.onReject = null
}
