import { createRouter, createWebHistory } from 'vue-router'
import { session, refreshSession } from './session'
import LoginView from './views/LoginView.vue'
import FolderView from './views/FolderView.vue'
import RecordEditView from './views/RecordEditView.vue'
import CreateRecordView from './views/CreateRecordView.vue'
import AuditsView from './views/AuditsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    {
      path: '/',
      name: 'folder',
      component: FolderView,
      props: { folderKey: 'edit' },
      meta: { requiresAuth: true },
    },
    {
      path: '/create',
      name: 'create',
      component: CreateRecordView,
      meta: { requiresAuth: true },
    },
    {
      path: '/audits',
      name: 'audits',
      component: AuditsView,
      meta: { requiresAuth: true },
    },
    {
      path: '/review',
      name: 'review',
      component: FolderView,
      props: { folderKey: 'pending' },
      meta: { requiresAuth: true },
    },
    {
      // The trailing (.*) lets relPath contain '/' for records in
      // subfolders (e.g. collectionA/foo.xml), matching the API's own
      // <path:rel_path> route converter. folderKey is 'edit' or
      // 'pending' -- which locations are actually browsable/openable
      // is enforced server-side (records_common.ALLOWED_FOLDERS).
      path: '/records/:folderKey/:relPath(.*)',
      name: 'record',
      component: RecordEditView,
      props: true,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  if (!session.checked) {
    await refreshSession()
  }
  if (to.meta.requiresAuth && !session.username) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && session.username) {
    return { name: 'folder' }
  }
  return true
})

export default router
