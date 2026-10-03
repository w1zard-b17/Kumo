<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import Toggle from '../components/Toggle.svelte'
  import Modal from '../components/Modal.svelte'
  import { get, patch, post, del } from '../lib/api.js'
  import { app, fail, toast, loadCategories, loadStorage, loadSettings } from '../lib/store.svelte.js'
  import { bytes, pct, LANGUAGES } from '../lib/format.js'

  const ICON_CHOICES = ['film', 'leaf', 'atom', 'scroll', 'users', 'cpu', 'fingerprint', 'user', 'palette', 'trophy', 'globe', 'mic', 'bolt', 'layers', 'star', 'cloud', 'calendar', 'dots']

  let s = $state({ ...app.settings })
  let system = $state(null)
  let tags = $state([])
  let newCat = $state('')
  let iconFor = $state(null) // category being given a new icon
  let removeCat = $state(null)
  let naming = $state(app.settings?.naming || '{title}')

  onMount(() => {
    loadStorage()
    get('/system').then((r) => (system = r)).catch(fail)
    get('/tags').then((t) => (tags = t)).catch(() => {})
    if (location.hash) setTimeout(() => document.querySelector(location.hash)?.scrollIntoView({ behavior: 'smooth' }), 100)
  })

  async function set(key, value) {
    try {
      app.settings = await patch('/settings', { [key]: value })
      s = { ...app.settings }
    } catch (e) {
      fail(e)
      s = { ...app.settings }
    }
  }

  const namingPreview = $derived(
    naming
      .replace('{title}', 'Cosmos: A Spacetime Odyssey')
      .replace('{year}', '2014')
      .replace('{channel}', 'National Geographic')
      .replace('{youtube_id}', 'dQw4w9WgXcQ')
      .replace('{type}', 'Docuseries'),
  )

  async function addCategory() {
    if (!newCat.trim()) return
    try {
      await post('/categories', { name: newCat.trim(), icon: 'film' })
      newCat = ''
      loadCategories()
    } catch (e) {
      fail(e)
    }
  }

  async function updateCategory(c, body) {
    try {
      const r = await patch(`/categories/${c.id}`, body)
      if (r.errors?.length) toast(`${r.errors.length} files could not be moved`, { kind: 'error' })
      else if (body.name) toast('Renamed, folder updated on storage', { kind: 'success' })
      loadCategories()
    } catch (e) {
      fail(e)
      loadCategories()
    }
  }

  async function deleteCategory() {
    try {
      const r = await del(`/categories/${removeCat.id}`)
      toast(r.unsorted ? `${r.unsorted} title${r.unsorted === 1 ? '' : 's'} moved to Unsorted` : 'Category deleted')
      removeCat = null
      loadCategories()
    } catch (e) {
      fail(e)
    }
  }

  async function renameTag(t, name) {
    if (!name.trim() || name === t.name) return
    try {
      await patch(`/tags/${t.id}`, { name: name.trim() })
      tags = await get('/tags')
    } catch (e) {
      fail(e)
    }
  }

  async function deleteTag(t) {
    try {
      await del(`/tags/${t.id}`)
      tags = tags.filter((x) => x.id !== t.id)
    } catch (e) {
      fail(e)
    }
  }

  async function logout() {
    await post('/auth/logout')
    location.reload()
  }
</script>

<header class="mb-10">
  <p class="label">Preferences</p>
  <h1 class="mt-2 text-3xl font-semibold tracking-tight">Settings</h1>
</header>

<div class="max-w-3xl space-y-12">
  <!-- storage -->
  <section id="storage" class="scroll-mt-10">
    <h2 class="label mb-4">Storage</h2>
    <div class="card p-6">
      {#if !app.storage}
        <div class="skeleton h-16 rounded-xl"></div>
      {:else if !app.storage.reachable}
        <div class="flex items-start gap-3">
          <span class="mt-1.5 size-2 shrink-0 rounded-full border border-white/70"></span>
          <div>
            <p class="font-medium">Storage host unreachable</p>
            <p class="mt-1 text-sm text-white/50">{app.storage.error}</p>
            <p class="mt-3 text-xs text-white/40">Check <span class="font-mono">rcctl check kumo_agent</span> on the host and the token in <span class="font-mono">/etc/kumo/kumo.env</span>.</p>
          </div>
        </div>
      {:else}
        {@const st = app.storage}
        {@const total = st.quota || st.disk_total}
        {@const used = st.quota ? st.used : st.disk_total - st.disk_free}
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="flex items-center gap-3">
            <span class="grid size-10 place-items-center rounded-xl border border-white/10 text-accent"><Icon name="hdd" size={19} /></span>
            <div>
              <p class="font-medium">{st.disk}</p>
              <p class="text-xs {st.online ? 'text-accent' : 'text-white/60'}">{st.online ? 'Online' : 'Offline, the disk is not mounted on the host'}</p>
            </div>
          </div>
          <div class="text-right">
            <p class="tabular text-2xl font-semibold tracking-tight">{bytes(st.available)}</p>
            <p class="label mt-1">available</p>
          </div>
        </div>
        {#if st.online}
          <div class="mt-6 h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
            <div class="h-full rounded-full bg-accent" style="width:{pct(used, total)}%"></div>
          </div>
          <div class="tabular mt-3 flex flex-wrap justify-between gap-2 text-xs text-white/45">
            <span>Kumo uses {bytes(st.used)}</span>
            <span>{st.quota ? `Quota ${bytes(st.quota)}` : `Disk ${bytes(st.disk_free)} free of ${bytes(st.disk_total)}`}</span>
          </div>
        {/if}
      {/if}
      {#if system}
        <div class="tabular mt-6 flex flex-wrap justify-between gap-2 border-t border-white/[0.06] pt-4 text-xs text-white/45">
          <span>VM temp disk: {bytes(system.tmp.free)} free</span>
          <span class="font-mono">{system.agent_url}</span>
        </div>
      {/if}
    </div>
  </section>

  <!-- downloads -->
  {#if app.settings}
    <section>
      <h2 class="label mb-4">Downloads</h2>
      <div class="card divide-y divide-white/[0.05] px-6">
        <div class="flex flex-wrap items-center justify-between gap-4 py-4">
          <span class="text-sm">Default quality</span>
          <div class="seg">
            {#each [['720', '720p'], ['1080', '1080p'], ['best', 'Best']] as [q, label] (q)}
              <button aria-pressed={s.quality === q} onclick={() => set('quality', q)}>{label}</button>
            {/each}
          </div>
        </div>
        <div class="py-4"><Toggle checked={s.subtitles} label="Download subtitles by default" onchange={(v) => set('subtitles', v)} /></div>
        <div class="flex items-center justify-between gap-6 py-4">
          <span class="text-sm">Subtitle language</span>
          <select class="field !w-44" value={s.sub_lang} onchange={(e) => set('sub_lang', e.target.value)}>
            {#each LANGUAGES.filter(([c]) => c) as [code, name]}<option value={code}>{name}</option>{/each}
          </select>
        </div>
        <div class="py-4"><Toggle checked={s.auto_subs} label="Allow auto-generated captions" onchange={(v) => set('auto_subs', v)} /></div>
        <div class="py-4"><Toggle checked={s.audio_fallback} label="Audio-only fallback" hint="Keep the audio when no video format is available" onchange={(v) => set('audio_fallback', v)} /></div>
      </div>
    </section>

    <!-- library -->
    <section>
      <h2 class="label mb-4">Library</h2>
      <div class="card divide-y divide-white/[0.05] px-6">
        <div class="py-5">
          <label for="naming" class="text-sm">File naming</label>
          <p class="mt-0.5 text-xs text-white/40">
            Tokens: <span class="font-mono text-white/60">{'{title} {year} {channel} {type} {youtube_id}'}</span>. Applies to new downloads.
          </p>
          <div class="mt-3 flex gap-2">
            <input id="naming" class="field font-mono !text-[13px]" bind:value={naming} />
            <button class="btn-ghost shrink-0" disabled={naming === s.naming} onclick={() => set('naming', naming)}>Save</button>
          </div>
          <p class="mt-2.5 truncate font-mono text-xs text-white/40">/library/Science/<span class="text-accent">{namingPreview}</span>.mp4</p>
        </div>
        <div class="flex items-center justify-between gap-6 py-4">
          <span class="text-sm">Default language for new titles</span>
          <select class="field !w-44" value={s.language} onchange={(e) => set('language', e.target.value)}>
            {#each LANGUAGES as [code, name]}<option value={code}>{code ? name : 'From YouTube'}</option>{/each}
          </select>
        </div>
        <div class="py-4"><Toggle checked={s.autoplay_next} label="Autoplay next in series or category" onchange={(v) => set('autoplay_next', v)} /></div>
      </div>
    </section>
  {/if}

  <!-- categories -->
  <section>
    <h2 class="label mb-4">Categories</h2>
    <div class="card divide-y divide-white/[0.05]">
      {#each app.categories as c (c.id)}
        <div class="flex items-center gap-3 px-4 py-2.5">
          <button class="btn-icon shrink-0 text-accent" onclick={() => (iconFor = c)} aria-label="Change icon" title="Change icon"><Icon name={c.icon} size={17} /></button>
          <input
            class="min-w-0 flex-1 rounded-lg bg-transparent px-2 py-1.5 text-sm outline-none hover:bg-white/[0.03] focus:bg-white/[0.04]"
            value={c.name}
            maxlength="40"
            onchange={(e) => e.target.value.trim() && e.target.value !== c.name && updateCategory(c, { name: e.target.value.trim() })}
            aria-label="Category name"
          />
          <span class="tabular w-10 text-right text-xs text-white/35">{c.count}</span>
          <button class="btn-icon shrink-0" onclick={() => (removeCat = c)} aria-label="Delete {c.name}"><Icon name="trash" size={15} /></button>
        </div>
      {/each}
      <form
        class="flex items-center gap-3 px-4 py-2.5"
        onsubmit={(e) => {
          e.preventDefault()
          addCategory()
        }}
      >
        <span class="grid size-9 shrink-0 place-items-center text-white/30"><Icon name="plus" size={17} /></span>
        <input class="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-white/30" bind:value={newCat} placeholder="New category" maxlength="40" />
        {#if newCat.trim()}<button class="btn-primary !py-1.5 text-xs">Add</button>{/if}
      </form>
    </div>
    <p class="mt-3 text-xs text-white/35">Renaming a category renames its folder on the storage disk. Deleting one moves its titles to Unsorted.</p>
  </section>

  <!-- tags -->
  <section>
    <h2 class="label mb-4">Tags</h2>
    {#if tags.length}
      <div class="card flex flex-wrap gap-2 p-4">
        {#each tags as t (t.id)}
          <span class="group inline-flex items-center rounded-full border border-white/10 py-0.5 pr-1 pl-1 text-xs transition-colors hover:border-white/25">
            <input
              class="bg-transparent px-2 py-0.5 text-white/80 outline-none focus:text-white"
              style="width:{Math.max(3, t.name.length + 1)}ch"
              value={t.name}
              onchange={(e) => renameTag(t, e.target.value)}
              aria-label="Tag name"
            />
            <span class="tabular pr-1 text-white/30">{t.count}</span>
            <button class="rounded-full p-1 text-white/30 hover:text-white" onclick={() => deleteTag(t)} aria-label="Delete tag {t.name}"><Icon name="x" size={11} /></button>
          </span>
        {/each}
      </div>
    {:else}
      <p class="text-sm text-white/35">Tags appear here once you add them while classifying.</p>
    {/if}
  </section>

  <!-- system -->
  <section>
    <h2 class="label mb-4">System</h2>
    <dl class="card divide-y divide-white/[0.05] text-sm">
      {#if system}
        {#each [
          ['Kumo', system.version],
          ['yt-dlp', system.yt_dlp || 'not installed'],
          ['ffmpeg', system.ffmpeg ? 'found' : 'missing, run apk add ffmpeg'],
          ['Storage agent', system.agent.reachable ? `kumo-agent ${system.agent.version}` : system.agent.error],
          ['Database', bytes(system.db_size)],
          ['Login', system.auth ? 'Password protected' : 'Open on the LAN (set KUMO_PASSWORD to protect)'],
        ] as [k, val]}
          <div class="flex justify-between gap-6 px-6 py-3.5">
            <dt class="text-white/45">{k}</dt>
            <dd class="tabular text-right text-white/85">{val}</dd>
          </div>
        {/each}
      {:else}
        <div class="skeleton m-6 h-24 rounded-xl"></div>
      {/if}
    </dl>
    <p class="mt-3 text-xs leading-relaxed text-white/35">
      When YouTube changes break downloads, update yt-dlp on the VM with <span class="font-mono text-white/55">/opt/kumo/update-ytdlp.sh</span> (also runs weekly).
    </p>
    {#if system?.auth}
      <button class="btn-ghost mt-6" onclick={logout}><Icon name="logout" size={15} /> Log out</button>
    {/if}
  </section>
</div>

<Modal open={!!iconFor} title="Icon for {iconFor?.name}" onclose={() => (iconFor = null)}>
  <div class="grid grid-cols-6 gap-2">
    {#each ICON_CHOICES as name}
      <button
        class="grid aspect-square place-items-center rounded-xl border transition-colors {iconFor?.icon === name ? 'border-accent text-accent' : 'border-white/[0.08] text-white/60 hover:border-white/25 hover:text-white'}"
        onclick={async () => {
          await updateCategory(iconFor, { icon: name })
          iconFor = null
        }}
        aria-label={name}
      >
        <Icon {name} size={20} />
      </button>
    {/each}
  </div>
</Modal>

<Modal open={!!removeCat} title="Delete “{removeCat?.name}”?" onclose={() => (removeCat = null)}>
  <p class="text-sm leading-relaxed text-white/65">
    {removeCat?.count ? `Its ${removeCat.count} title${removeCat.count === 1 ? '' : 's'} move to Unsorted, on disk too.` : 'No titles use it.'}
  </p>
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (removeCat = null)}>Cancel</button>
    <button class="btn border border-white bg-white text-ink hover:bg-white/85" onclick={deleteCategory}>Delete</button>
  {/snippet}
</Modal>
