// Thin wrapper around the webapp/ JSON API. Every call sends the
// session cookie (credentials: 'include') so Flask's signed-cookie
// session -- the only server-side auth state -- rides along
// automatically once /api/auth/login has set it.

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  const contentType = res.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await res.json() : null

  if (!res.ok) {
    throw new ApiError((data && data.error) || `Request failed (${res.status})`, res.status)
  }
  return data
}

export const api = {
  login: (username, password) => request('POST', '/api/auth/login', { username, password }),
  logout: () => request('POST', '/api/auth/logout'),
  whoami: () => request('GET', '/api/auth/whoami'),

  listFolder: (key) => request('GET', `/api/folders/${key}`),

  openRecord: (key, relPath) => request('GET', `/api/records/${key}/${relPath}`),
  heartbeat: (key, relPath) => request('POST', `/api/records/${key}/${relPath}/heartbeat`),
  release: (key, relPath) => request('POST', `/api/records/${key}/${relPath}/release`),
  save: (key, relPath, edits, commitMessage) =>
    request('PUT', `/api/records/${key}/${relPath}`, { edits, commit_message: commitMessage || undefined }),
  submit: (key, relPath, commitMessage) =>
    request('POST', `/api/records/${key}/${relPath}/submit`, { commit_message: commitMessage || undefined }),
  approve: (key, relPath, commitMessage) =>
    request('POST', `/api/records/${key}/${relPath}/approve`, { commit_message: commitMessage || undefined }),
  reject: (key, relPath, reason, commitMessage) =>
    request('POST', `/api/records/${key}/${relPath}/reject`, {
      reason: reason || undefined, commit_message: commitMessage || undefined,
    }),

  addNote: (key, relPath, text) => request('POST', `/api/records/${key}/${relPath}/notes`, { text }),
  updateNote: (key, relPath, index, resolved) =>
    request('PUT', `/api/records/${key}/${relPath}/notes/${index}`, { resolved }),
  deleteNote: (key, relPath, index) => request('DELETE', `/api/records/${key}/${relPath}/notes/${index}`),
}

export { ApiError }
