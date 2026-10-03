<script>
  import Icon from '../components/Icon.svelte'
  import VideoCard from '../components/VideoCard.svelte'
  import Empty from '../components/Empty.svelte'
  import Modal from '../components/Modal.svelte'
  import BulkModals from '../components/BulkModals.svelte'
  import { get, post } from '../lib/api.js'
  import { app, fail, toast, loadCategories, loadStorage } from '../lib/store.svelte.js'
  import { route, setQuery } from '../lib/router.svelte.js'
  import { duration, ago, TYPE_ICONS, LANGUAGES } from '../lib/format.js'

  const PAGE = 120
  const DURATIONS = {
    short: [null, 1800, '< 30m'],
    mid: [1800, 3600, '30–60m'],
    long: [3600, 7200, '1–2h'],
    epic: [7200, null, '2h +'],
  }
  const SORTS = [
    ['added', 'Date added'],
    ['title', 'Title'],
    ['duration', 'Duration'],
    ['last_watched', 'Last watched'],
    ['year', 'Year'],
    ['rating', 'Rating'],
  ]

  // Filters live in the URL so back/forward and reloads keep them.
  const q = $derived(route.query)
  const view = $derived(q.get('view') || 'grid')
  const sort = $derived(q.get('sort') || 'added')
  const order = $derived(q.get('order') || (sort === 'title' ? 'asc' : 'desc'))
  const categories = $derived(q.getAll('category').map(Number))
  const unsorted = $derived(q.get('unsorted') === '1')
  const types = $derived(q.getAll('type'))
  const tagsSel = $derived(q.getAll('tag'))
  const watched = $derived(q.get('watched') || '')
  const dur = $derived(q.get('dur') || '')
  const language = $derived(q.get('language') || '')
  const yearFrom = $derived(q.get('year_from') || '')
  const yearTo = $derived(q.get('year_to') || '')

  let search = $state(route.query.get('q') || '')
  let items = $state([])
  let total = $state(0)
  let loading = $state(true)
  let showFilters = $state(false)
  let allTags = $state([])
  let selecting = $state(false)
  let selected = $state([])
  let bulk = $state(null)
  let confirmDelete = $state(false)

  const activeFilters = $derived(
    types.length + tagsSel.length + (watched ? 1 : 0) + (dur ? 1 : 0) + (language ? 1 : 0) + (yearFrom || yearTo ? 1 : 0),
  )

  function params(offset = 0) {
    const [dmin, dmax] = DURATIONS[dur] || []
    return {
      q: q.get('q') || '',
      category: categories,
      unsorted: unsorted ? 'true' : '',
      type: types,
      tag: tagsSel,
      watched: watched === 'yes' ? 'true' : watched === 'no' ? 'false' : '',
      dur_min: dmin ?? '',
      dur_max: dmax ?? '',
      language,
      year_from: yearFrom,
      year_to: yearTo,
      sort,
      order,
      limit: PAGE,
      offset,
    }
  }

  let ctrl
  async function load(append = false) {
    ctrl?.abort()
    ctrl = new AbortController()
    loading = true
    try {
      const r = await get('/videos', params(append ? items.length : 0), { signal: ctrl.signal })
      items = append ? [...items, ...r.items] : r.items
      total = r.total
      loading = false
    } catch (e) {
      if (e.name !== 'AbortError') {
        fail(e)
        loading = false
      }
    }
  }

  $effect(() => {
    // re-query whenever the URL filters change
    route.query.toString()
    load()
  })

  $effect(() => {
    if (showFilters && !allTags.length) get('/tags').then((t) => (allTags = t)).catch(() => {})
  })

  let debounce
  function onSearch() {
    clearTimeout(debounce)
    debounce = setTimeout(() => setQuery({ q: search.trim() }), 220)
  }

  function toggleIn(key, list, value) {
    setQuery({ [key]: list.includes(value) ? list.filter((x) => x !== value) : [...list, value] })
  }

  function toggleSelect(v) {
    selected = selected.includes(v.id) ? selected.filter((x) => x !== v.id) : [...selected, v.id]
  }

  function endSelect() {
    selecting = false
    selected = []
  }

  async function bulkAction(action) {
    try {
      const r = await post('/videos/bulk', { ids: selected, action })
      toast(action === 'delete' ? `Deleted ${r.done}` : `Updated ${r.done}`, { kind: 'success' })
      if (r.errors.length) toast(`${r.errors.length} failed: ${r.errors[0].error}`, { kind: 'error' })
      confirmDelete = false
      endSelect()
      load()
      loadCategories()
      loadStorage()
    } catch (e) {
      fail(e)
    }
  }

  const groups = $derived.by(() => {
    if (view !== 'grouped') return []
    const map = new Map()
    for (const v of items) {
      const key = v.category?.name || 'Unsorted'
      if (!map.has(key)) map.set(key, { name: key, icon: v.category?.icon || 'inbox', items: [] })
      map.get(key).items.push(v)
    }
    const order = app.categories.map((c) => c.name)
    return [...map.values()].sort((a, b) => {
      const ia = order.indexOf(a.name)
      const ib = order.indexOf(b.name)
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
    })
  })
</script>

<header class="mb-8 flex flex-wrap items-end justify-between gap-4">
  <div>
    <p class="label">Collection of {total} title{total === 1 ? '' : 's'}</p>
    <h1 class="mt-2 text-3xl font-semibold tracking-tight">Library</h1>
  </div>
  <div class="flex items-center gap-2">
    {#if selecting}
      <button class="btn-quiet" onclick={() => (selected = selected.length === items.length ? [] : items.map((v) => v.id))}>
        {selected.length === items.length ? 'None' : 'All'}
      </button>
      <button class="btn-ghost" onclick={endSelect}>Done</button>
    {:else}
      <button class="btn-quiet" onclick={() => (selecting = true)} disabled={!items.length}><Icon name="select" size={16} /> Select</button>
    {/if}
  </div>
</header>

<!-- toolbar -->
<div class="sticky top-[57px] z-20 -mx-4 mb-6 border-b border-white/[0.06] bg-ink/85 px-4 pt-1 pb-4 backdrop-blur-xl sm:-mx-6 sm:px-6 md:top-0 md:-mx-10 md:px-10 md:pt-4">
  <div class="flex flex-wrap items-center gap-2">
    <label class="relative min-w-0 flex-1 basis-60">
      <Icon name="search" size={16} class="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-white/35" />
      <input class="field !rounded-full !pl-10" type="search" placeholder="Search titles, descriptions, tags…" bind:value={search} oninput={onSearch} />
    </label>
    <button class="btn-ghost relative h-10" aria-expanded={showFilters} onclick={() => (showFilters = !showFilters)}>
      <Icon name="filter" size={16} /> Filters
      {#if activeFilters}<span class="tabular grid size-5 place-items-center rounded-full bg-accent text-[10px] font-semibold text-ink">{activeFilters}</span>{/if}
    </button>
    <div class="flex items-center">
      <select class="field !h-10 !w-auto !rounded-full !py-0 !text-xs" value={sort} onchange={(e) => setQuery({ sort: e.target.value, order: '' })} aria-label="Sort by">
        {#each SORTS as [k, label]}<option value={k}>{label}</option>{/each}
      </select>
      <button class="btn-icon ml-1" onclick={() => setQuery({ order: order === 'asc' ? 'desc' : 'asc' })} aria-label="Reverse order" title={order === 'asc' ? 'Ascending' : 'Descending'}>
        <Icon name="sort" size={16} class={order === 'asc' ? 'text-accent' : ''} />
      </button>
    </div>
    <div class="seg !p-0.5">
      {#each [['grid', 'grid'], ['list', 'list'], ['grouped', 'rows']] as [v, icon] (v)}
        <button aria-pressed={view === v} onclick={() => setQuery({ view: v === 'grid' ? '' : v })} aria-label="{v} view" class="!px-2.5">
          <Icon name={icon} size={15} />
        </button>
      {/each}
    </div>
  </div>

  <div class="mt-3 -mb-1 flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
    <button class="chip shrink-0 {!categories.length && !unsorted ? 'chip-on' : ''}" onclick={() => setQuery({ category: [], unsorted: '' })}>All</button>
    {#if app.unsorted}
      <button class="chip shrink-0 {unsorted ? 'chip-on' : ''}" onclick={() => setQuery({ unsorted: unsorted ? '' : '1', category: [] })}>
        <Icon name="inbox" size={13} /> Unsorted <span class="tabular opacity-60">{app.unsorted}</span>
      </button>
    {/if}
    {#each app.categories.filter((c) => c.count) as c (c.id)}
      <button class="chip shrink-0 {categories.includes(c.id) ? 'chip-on' : ''}" onclick={() => { setQuery({ unsorted: '' }); toggleIn('category', categories, c.id) }}>
        <Icon name={c.icon} size={13} /> {c.name} <span class="tabular opacity-50">{c.count}</span>
      </button>
    {/each}
  </div>

  {#if showFilters}
    <div class="rise mt-4 grid gap-6 rounded-2xl border border-white/[0.07] bg-coal p-5 md:grid-cols-2 xl:grid-cols-4">
      <div>
        <p class="label mb-2.5">Type</p>
        <div class="flex flex-wrap gap-1.5">
          {#each Object.entries(app.types) as [k, label] (k)}
            <button class="chip {types.includes(k) ? 'chip-on' : ''}" onclick={() => toggleIn('type', types, k)}>
              <Icon name={TYPE_ICONS[k]} size={13} />{label}
            </button>
          {/each}
        </div>
      </div>
      <div>
        <p class="label mb-2.5">Duration</p>
        <div class="flex flex-wrap gap-1.5">
          {#each Object.entries(DURATIONS) as [k, [, , label]] (k)}
            <button class="chip {dur === k ? 'chip-on' : ''}" onclick={() => setQuery({ dur: dur === k ? '' : k })}>{label}</button>
          {/each}
        </div>
      </div>
      <div>
        <p class="label mb-2.5">Watched</p>
        <div class="seg">
          {#each [['', 'All'], ['no', 'Unwatched'], ['yes', 'Watched']] as [k, label] (k)}
            <button aria-pressed={watched === k} onclick={() => setQuery({ watched: k })}>{label}</button>
          {/each}
        </div>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <p class="label mb-2.5">Year</p>
          <div class="flex items-center gap-1.5">
            <input class="field tabular !px-2.5 !py-1.5 !text-xs" type="number" placeholder="from" value={yearFrom} onchange={(e) => setQuery({ year_from: e.target.value })} />
            <input class="field tabular !px-2.5 !py-1.5 !text-xs" type="number" placeholder="to" value={yearTo} onchange={(e) => setQuery({ year_to: e.target.value })} />
          </div>
        </div>
        <div>
          <p class="label mb-2.5">Language</p>
          <select class="field !py-1.5 !text-xs" value={language} onchange={(e) => setQuery({ language: e.target.value })}>
            {#each LANGUAGES as [code, name]}<option value={code}>{name}</option>{/each}
          </select>
        </div>
      </div>
      {#if allTags.length}
        <div class="md:col-span-2 xl:col-span-4">
          <p class="label mb-2.5">Tags</p>
          <div class="flex flex-wrap gap-1.5">
            {#each allTags.filter((t) => t.count) as t (t.id)}
              <button class="chip {tagsSel.includes(t.name) ? 'chip-on' : ''}" onclick={() => toggleIn('tag', tagsSel, t.name)}>
                {t.name} <span class="tabular opacity-50">{t.count}</span>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      {#if activeFilters}
        <div class="md:col-span-2 xl:col-span-4">
          <button class="btn-quiet -ml-3 text-xs" onclick={() => setQuery({ type: [], tag: [], watched: '', dur: '', language: '', year_from: '', year_to: '' })}>
            <Icon name="x" size={14} /> Clear filters
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

{#if loading && !items.length}
  <div class="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
    {#each Array(10) as _}
      <div><div class="skeleton aspect-video rounded-xl"></div><div class="skeleton mt-3 h-3 w-3/4 rounded"></div></div>
    {/each}
  </div>
{:else if !items.length}
  {#if q.toString() && q.toString() !== 'view=list' && q.toString() !== 'view=grouped'}
    <Empty icon="search" title="Nothing matches" text="Try fewer filters or a different search.">
      <button class="btn-ghost" onclick={() => { search = ''; setQuery({ q: '', category: [], unsorted: '', type: [], tag: [], watched: '', dur: '', language: '', year_from: '', year_to: '' }) }}>Reset</button>
    </Empty>
  {:else}
    <Empty icon="library" title="Your library is empty" text="Paste a YouTube link to download and file your first documentary.">
      <a href="/" class="btn-primary">Add a link</a>
    </Empty>
  {/if}
{:else if view === 'list'}
  <div class="card overflow-hidden">
    <table class="w-full text-left text-sm">
      <thead class="label border-b border-white/[0.06]">
        <tr>
          <th class="py-3 pl-5 font-medium">Title</th>
          <th class="hidden py-3 font-medium md:table-cell">Category</th>
          <th class="hidden py-3 font-medium lg:table-cell">Year</th>
          <th class="hidden py-3 font-medium sm:table-cell">Length</th>
          <th class="hidden py-3 font-medium xl:table-cell">Added</th>
          <th class="py-3 pr-5 text-right font-medium"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-white/[0.04]">
        {#each items as v (v.id)}
          {@const on = selected.includes(v.id)}
          <tr class="group transition-colors hover:bg-white/[0.02] {on ? 'bg-accent/[0.05]' : ''}">
            <td class="py-2.5 pl-5">
              <a
                href="/v/{v.id}"
                class="flex items-center gap-4"
                onclick={(e) => {
                  if (selecting) {
                    e.preventDefault()
                    toggleSelect(v)
                  }
                }}
              >
                {#if selecting}
                  <span class="grid size-5 shrink-0 place-items-center rounded-full border-2 {on ? 'border-accent bg-accent text-ink' : 'border-white/30 text-transparent'}">
                    <Icon name="check" size={11} stroke={2.6} />
                  </span>
                {/if}
                <img src={v.poster} alt="" loading="lazy" class="aspect-video w-24 shrink-0 rounded-md bg-char object-cover" />
                <span class="min-w-0">
                  <span class="line-clamp-1 font-medium text-white/95">{v.title}</span>
                  <span class="mt-0.5 block truncate text-xs text-white/40">{v.channel}</span>
                </span>
              </a>
            </td>
            <td class="hidden text-white/60 md:table-cell">{v.category?.name || 'Unsorted'}</td>
            <td class="tabular hidden text-white/60 lg:table-cell">{v.year || '—'}</td>
            <td class="tabular hidden text-white/60 sm:table-cell">{duration(v.duration)}</td>
            <td class="hidden text-white/40 xl:table-cell">{ago(v.added_at)}</td>
            <td class="pr-5 text-right">
              {#if v.playback.watched}<Icon name="check" size={16} class="inline text-accent" />{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else if view === 'grouped'}
  <div class="space-y-12">
    {#each groups as g (g.name)}
      <section>
        <h2 class="mb-4 flex items-center gap-2.5 text-[15px] font-semibold">
          <span class="text-accent"><Icon name={g.icon} size={17} /></span>{g.name}
          <span class="tabular text-xs font-normal text-white/35">{g.items.length}</span>
        </h2>
        <div class="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 scrollbar-none sm:-mx-6 sm:px-6 md:-mx-10 md:px-10">
          {#each g.items as v (v.id)}
            <div class="w-60 shrink-0 snap-start sm:w-64">
              <VideoCard video={v} size="sm" selectable={selecting} selected={selected.includes(v.id)} onselect={toggleSelect} />
            </div>
          {/each}
        </div>
      </section>
    {/each}
  </div>
{:else}
  <div class="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
    {#each items as v (v.id)}
      <VideoCard video={v} selectable={selecting} selected={selected.includes(v.id)} onselect={toggleSelect} />
    {/each}
  </div>
{/if}

{#if items.length < total}
  <div class="mt-10 text-center">
    <button class="btn-ghost" onclick={() => load(true)} disabled={loading}>Load more <span class="tabular text-white/40">{total - items.length}</span></button>
  </div>
{/if}

{#if selecting && selected.length}
  <div class="rise fixed inset-x-0 bottom-20 z-40 flex justify-center px-4 md:bottom-8 md:pl-60">
    <div class="flex max-w-full items-center gap-1 overflow-x-auto rounded-full border border-white/10 bg-char/95 p-1.5 pl-5 shadow-2xl shadow-black backdrop-blur-xl scrollbar-none">
      <span class="tabular mr-2 shrink-0 text-sm"><span class="text-accent">{selected.length}</span> selected</span>
      <button class="btn-quiet shrink-0 !py-1.5" onclick={() => (bulk = 'reclassify')}><Icon name="tag" size={15} /> Reclassify</button>
      <button class="btn-quiet shrink-0 !py-1.5" onclick={() => (bulk = 'tags')}><Icon name="plus" size={15} /> Tags</button>
      <button class="btn-quiet shrink-0 !py-1.5" onclick={() => (bulk = 'collection')}><Icon name="layers" size={15} /> Collection</button>
      <button class="btn-quiet shrink-0 !py-1.5" onclick={() => bulkAction('watched')}><Icon name="eye" size={15} /> Watched</button>
      <button class="btn-quiet shrink-0 !py-1.5" onclick={() => (confirmDelete = true)}><Icon name="trash" size={15} /> Delete</button>
      <button class="btn-icon shrink-0" onclick={endSelect} aria-label="Clear selection"><Icon name="x" size={16} /></button>
    </div>
  </div>
{/if}

<BulkModals bind:mode={bulk} ids={selected} ondone={() => { endSelect(); load() }} />

<Modal open={confirmDelete} title="Delete {selected.length} title{selected.length === 1 ? '' : 's'}?" onclose={() => (confirmDelete = false)}>
  <p class="text-sm leading-relaxed text-white/65">The MP4, poster and subtitles are removed from the storage disk. This can't be undone.</p>
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (confirmDelete = false)}>Cancel</button>
    <button class="btn border border-white bg-white text-ink hover:bg-white/85" onclick={() => bulkAction('delete')}>Delete</button>
  {/snippet}
</Modal>
