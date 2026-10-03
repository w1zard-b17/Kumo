export function duration(sec) {
  sec = Math.round(sec || 0)
  if (!sec) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (h) return m ? `${h}h ${m}m` : `${h}h`
  if (m) return `${m}m`
  return `${sec}s`
}

export function clock(sec) {
  sec = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = String(sec % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

export function bytes(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  if (n < 1024) return `${Math.round(n)} B`
  const units = ['KB', 'MB', 'GB', 'TB', 'PB']
  let i = -1
  do {
    n /= 1024
    i++
  } while (n >= 1024 && i < units.length - 1)
  return `${n.toFixed(n >= 100 ? 0 : digits)} ${units[i]}`
}

export function speed(bps) {
  return bps ? `${bytes(bps)}/s` : ''
}

export function eta(sec) {
  if (!sec && sec !== 0) return ''
  if (sec < 60) return `${Math.max(1, Math.round(sec))}s left`
  if (sec < 3600) return `${Math.round(sec / 60)}m left`
  return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m left`
}

export function ago(ts) {
  if (!ts) return ''
  const d = Date.now() / 1000 - ts
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  if (d < 86400 * 7) return `${Math.floor(d / 86400)}d ago`
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function pct(part, whole) {
  return whole ? Math.min(100, Math.max(0, (part / whole) * 100)) : 0
}

export const TYPE_ICONS = { documentary: 'film', docuseries: 'layers', short: 'bolt', lecture: 'mic' }

export const LANGUAGES = [
  ['', 'Any'], ['en', 'English'], ['it', 'Italiano'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español'],
  ['pt', 'Português'], ['nl', 'Nederlands'], ['ja', '日本語'], ['zh', '中文'], ['ko', '한국어'], ['ru', 'Русский'],
  ['ar', 'العربية'], ['pl', 'Polski'], ['sv', 'Svenska'], ['tr', 'Türkçe'],
]

export function langName(code) {
  return LANGUAGES.find(([c]) => c === code)?.[1] || code || ''
}
