// Minimal reactive session state -- the server is the actual source of
// truth (a signed-cookie Flask session), this just mirrors "am I
// logged in, as whom" for the UI without pulling in a state-management
// library for what's a single value.

import { reactive } from 'vue'
import { api, ApiError } from './api'

export const session = reactive({
  username: null,
  checked: false, // true once the initial whoami check has resolved
})

export async function refreshSession() {
  try {
    const data = await api.whoami()
    session.username = data.username
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) throw e
    session.username = null
  } finally {
    session.checked = true
  }
}

export async function login(username, password) {
  const data = await api.login(username, password)
  session.username = data.username
}

export async function logout() {
  await api.logout()
  session.username = null
}
