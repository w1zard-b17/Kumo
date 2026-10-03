// Minimal history router; the app has too few routes to warrant a dependency.

export const route = $state({
  path: location.pathname,
  query: new URLSearchParams(location.search),
})

function sync() {
  route.path = location.pathname
  route.query = new URLSearchParams(location.search)
}

let depth = 0 // in-app history entries we pushed, so back() never leaves the app

export function navigate(to, { replace = false, scroll = true } = {}) {
  if (to === location.pathname + location.search) return
  if (!replace) depth++
  history[replace ? 'replaceState' : 'pushState']({}, '', to)
  sync()
  if (scroll) window.scrollTo({ top: 0 })
}

/** Update query params in place (filters, view mode) without adding history entries. */
export function setQuery(patch) {
  const q = new URLSearchParams(location.search)
  for (const [k, v] of Object.entries(patch)) {
    q.delete(k)
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x))
    else if (v !== undefined && v !== null && v !== '' && v !== false) q.set(k, v)
  }
  const s = q.toString()
  navigate(location.pathname + (s ? `?${s}` : ''), { replace: true, scroll: false })
}

export function back(fallback = '/') {
  if (depth > 0) history.back()
  else navigate(fallback, { replace: true })
}

/** match('/v/:id', '/v/12') -> { id: '12' } */
export function match(pattern, path) {
  const a = pattern.split('/').filter(Boolean)
  const b = path.split('/').filter(Boolean)
  if (a.length !== b.length) return null
  const params = {}
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith(':')) params[a[i].slice(1)] = decodeURIComponent(b[i])
    else if (a[i] !== b[i]) return null
  }
  return params
}

addEventListener('popstate', () => {
  depth = Math.max(0, depth - 1)
  sync()
})

// Intercept same-origin <a href="/..."> clicks app-wide.
document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  const a = e.target.closest?.('a[href]')
  if (!a || a.target || a.hasAttribute('download')) return
  const href = a.getAttribute('href')
  if (!href.startsWith('/') || href.startsWith('//') || href.startsWith('/api/')) return
  e.preventDefault()
  navigate(href)
})
