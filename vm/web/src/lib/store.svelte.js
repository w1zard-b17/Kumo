import { get, setUnauthorizedHandler } from './api.js'

export const app = $state({
  auth: null, // { required, authenticated }
  categories: [],
  types: {},
  unsorted: 0,
  settings: null,
  storage: null,
  active: [], // active download jobs
})

setUnauthorizedHandler(() => {
  app.auth = { required: true, authenticated: false }
})

export async function loadAuth() {
  app.auth = await get('/auth')
  return app.auth
}

export async function loadCategories() {
  const r = await get('/categories')
  app.categories = r.categories
  app.types = r.types
  app.unsorted = r.unsorted
}

export async function loadSettings() {
  app.settings = await get('/settings')
}

export async function loadStorage() {
  try {
    app.storage = await get('/storage')
  } catch {
    app.storage = { reachable: false }
  }
}

export function categoryById(id) {
  return app.categories.find((c) => c.id === id)
}

let timer = null
let listeners = new Set()

// Polls fast while something is running, slowly otherwise.
export async function refreshJobs() {
  try {
    const jobs = await get('/jobs', { state: 'active' })
    const wasRunning = app.active.map((j) => j.id)
    app.active = jobs
    const finished = wasRunning.filter((id) => !jobs.some((j) => j.id === id))
    if (finished.length) listeners.forEach((fn) => fn(finished))
  } catch {
    /* offline or logged out; the next tick retries */
  }
  schedule()
}

function schedule() {
  clearTimeout(timer)
  const busy = app.active.some((j) => ['downloading', 'converting', 'uploading'].includes(j.status))
  const waiting = app.active.length > 0
  timer = setTimeout(refreshJobs, busy ? 1500 : waiting ? 4000 : 15000)
}

/** Called with the ids of jobs that left the active list (done, failed, canceled). */
export function onJobsFinished(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const toasts = $state([])
let tid = 0

export function toast(message, { kind = 'info', action = null, timeout = 4200 } = {}) {
  const id = ++tid
  toasts.push({ id, message, kind, action })
  if (timeout) setTimeout(() => dismiss(id), timeout)
  return id
}

export function dismiss(id) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

export function fail(e) {
  toast(e?.message || String(e), { kind: 'error', timeout: 6000 })
}

export const draft = $state({ preview: null, selected: [], skip: false })
