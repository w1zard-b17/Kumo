<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import Modal from '../components/Modal.svelte'
  import ClassifyFields from '../components/ClassifyFields.svelte'
  import Rating from '../components/Rating.svelte'
  import TagInput from '../components/TagInput.svelte'
  import BulkModals from '../components/BulkModals.svelte'
  import ProgressBar from '../components/ProgressBar.svelte'
  import { get, patch, del } from '../lib/api.js'
  import { app, fail, toast, loadCategories, loadStorage, onJobsFinished } from '../lib/store.svelte.js'
  import { navigate, back } from '../lib/router.svelte.js'
  import { duration, clock, bytes, ago, langName, pct, TYPE_ICONS } from '../lib/format.js'

  let { params } = $props()
  let v = $state(null)
  let missing = $state(false)
  let editing = $state(false)
  let editTags = $state(false)
  let confirmDelete = $state(false)
  let collectionMode = $state(null)
  let form = $state(null)
  let tags = $state([])
  let allTags = $state([])
  let expanded = $state(false)
  let saving = $state(false)

  async function load() {
    try {
      v = await get(`/videos/${params.id}`)
    } catch (e) {
      if (e.status === 404) missing = true
      else fail(e)
    }
  }

  onMount(() => {
    load()
    return onJobsFinished(load)
  })

  const job = $derived(v?.job && v.status !== 'ready' ? app.active.find((j) => j.id === v.job.id) || v.job : null)
  const resumeAt = $derived(v && !v.playback.watched && v.playback.position > 30 ? v.playback.position : 0)
  const progress = $derived(v ? pct(v.playback.position, v.playback.duration || v.duration) : 0)

  function openEdit() {
    form = {
      title: v.title,
      description: v.description,
      type: v.type,
      category_id: v.category?.id ?? null,
      subcategory: v.subcategory,
      tags: [...v.tags],
      year: v.year,
      language: v.language,
    }
    get('/tags').then((t) => (allTags = t.map((x) => x.name))).catch(() => {})
    editing = true
  }

  async function save(body, msg = 'Saved') {
    saving = true
    try {
      v = await patch(`/videos/${v.id}`, body)
      toast(msg, { kind: 'success' })
      loadCategories()
      return true
    } catch (e) {
      fail(e)
      return false
    } finally {
      saving = false
    }
  }

  async function saveEdit() {
    const ok = await save({ ...form, year: form.year || null, category_id: form.category_id ?? undefined })
    if (ok) editing = false
  }

  async function remove() {
    try {
      await del(`/videos/${v.id}`)
      toast(`Deleted “${v.title}”`)
      loadCategories()
      loadStorage()
      navigate('/library', { replace: true })
    } catch (e) {
      fail(e)
    }
  }
</script>

{#if missing}
  <div class="py-24 text-center">
    <p class="text-white/60">This title isn't in the library anymore.</p>
    <a href="/library" class="btn-ghost mt-6">Back to library</a>
  </div>
{:else if !v}
  <div class="skeleton aspect-[21/9] w-full rounded-3xl"></div>
{:else}
  <!-- hero -->
  <section class="relative -mx-4 -mt-6 overflow-hidden sm:-mx-6 md:-mx-10 md:-mt-10">
    <img src={v.poster} alt="" class="absolute inset-0 size-full scale-110 object-cover opacity-35 blur-2xl" />
    <div class="absolute inset-0 bg-gradient-to-b from-black/30 via-black/70 to-black"></div>

    <div class="relative px-4 pt-6 pb-10 sm:px-6 md:px-10 md:pt-8 md:pb-14">
      <button class="btn-quiet -ml-3 mb-6 !px-3" onclick={() => back('/library')}><Icon name="arrow-left" size={16} /> Back</button>

      <div class="grid items-end gap-8 lg:grid-cols-[minmax(0,500px)_1fr] lg:gap-12">
        <a
          href={v.status === 'ready' ? `/watch/${v.id}` : null}
          class="group relative block aspect-video overflow-hidden rounded-2xl bg-char shadow-2xl shadow-black ring-1 ring-white/10"
        >
          <img src={v.poster} alt="" class="size-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" />
          {#if v.status === 'ready'}
            <span class="absolute inset-0 m-auto grid size-16 place-items-center rounded-full bg-accent text-ink opacity-90 shadow-xl transition-all group-hover:scale-105 group-hover:opacity-100">
              <Icon name="play" size={26} />
            </span>
          {/if}
          {#if progress > 0 && !v.playback.watched}
            <div class="absolute inset-x-0 bottom-0 h-1 bg-white/15"><div class="h-full bg-accent" style="width:{progress}%"></div></div>
          {/if}
        </a>

        <div class="min-w-0">
          <p class="label flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span class="inline-flex items-center gap-1.5 text-accent"><Icon name={TYPE_ICONS[v.type]} size={13} />{app.types[v.type]}</span>
            <span class="text-white/20">/</span>
            {#if v.category}
              <a href="/library?category={v.category.id}" class="hover:text-white">{v.category.name}</a>
            {:else}
              <span>Unsorted</span>
            {/if}
            {#if v.subcategory}
              <span class="text-white/20">/</span>
              <span class="normal-case tracking-normal text-white/60">{v.subcategory}</span>
            {/if}
          </p>
          <h1 class="mt-3 text-3xl leading-[1.12] font-semibold tracking-[-0.025em] text-balance md:text-[40px]">{v.title}</h1>

          <p class="tabular mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-white/55">
            {#if v.year}<span>{v.year}</span>{/if}
            <span>{duration(v.duration)}</span>
            {#if v.resolution}<span class="rounded border border-white/20 px-1.5 text-[11px] leading-5 text-white/70">{v.resolution === 'audio' ? 'AUDIO' : v.resolution.toUpperCase()}</span>{/if}
            {#if v.language}<span>{langName(v.language)}</span>{/if}
            {#if v.subtitles?.length}<span class="inline-flex items-center gap-1"><Icon name="cc" size={15} />{v.subtitles.map((s) => s.lang).join(', ')}</span>{/if}
            <span>{v.channel}</span>
          </p>

          <div class="mt-4"><Rating value={v.rating} onchange={(r) => save({ rating: r }, 'Rating saved')} size={17} /></div>

          <div class="mt-7 flex flex-wrap items-center gap-2">
            {#if v.status === 'ready'}
              <a href="/watch/{v.id}" class="btn-primary h-11 px-6">
                <Icon name="play" size={16} />
                {resumeAt ? `Resume ${clock(resumeAt)}` : v.playback.watched ? 'Watch again' : 'Play'}
              </a>
              {#if resumeAt}
                <a href="/watch/{v.id}?t=0" class="btn-quiet h-11 !px-3">From start</a>
              {/if}
            {/if}
            <button
              class="btn-ghost h-11 max-sm:w-11 max-sm:!px-0"
              title={v.playback.watched ? 'Mark unwatched' : 'Mark watched'}
              onclick={() => save({ watched: !v.playback.watched }, v.playback.watched ? 'Marked unwatched' : 'Marked watched')}
            >
              <Icon name={v.playback.watched ? 'eye-off' : 'check'} size={16} />
              <span class="hidden sm:inline">{v.playback.watched ? 'Unwatch' : 'Watched'}</span>
            </button>
            <button class="btn-icon size-11 border border-white/12" onclick={openEdit} aria-label="Edit" title="Edit"><Icon name="edit" size={17} /></button>
            <button class="btn-icon size-11 border border-white/12" onclick={() => (collectionMode = 'collection')} aria-label="Add to collection" title="Add to collection"><Icon name="layers" size={17} /></button>
            <button class="btn-icon size-11 border border-white/12" onclick={() => (confirmDelete = true)} aria-label="Delete" title="Delete"><Icon name="trash" size={17} /></button>
          </div>
        </div>
      </div>
    </div>
  </section>

  {#if job}
    <div class="card mt-2 flex items-center gap-4 p-5">
      <span class="text-accent"><Icon name="download" size={18} /></span>
      <div class="min-w-0 flex-1">
        <p class="text-sm">{job.status === 'failed' ? 'Download failed' : job.status === 'paused' ? 'Download paused' : 'Downloading…'} <span class="tabular text-white/40">{Math.round(job.progress)}%</span></p>
        {#if job.error}<p class="mt-1 text-xs text-white/55">{job.error}</p>{/if}
        <ProgressBar class="mt-3" value={job.progress} indeterminate={job.status === 'converting'} />
      </div>
      <a href="/downloads" class="btn-quiet text-xs">Open queue</a>
    </div>
  {/if}

  <div class="mt-10 grid gap-12 lg:grid-cols-[minmax(0,1fr)_320px]">
    <div class="min-w-0 space-y-12">
      <section>
        <h2 class="label mb-4">About</h2>
        {#if v.description}
          <p class="text-[15px] leading-relaxed whitespace-pre-line text-white/75 {expanded ? '' : 'line-clamp-6'}">{v.description}</p>
          {#if v.description.length > 420}
            <button class="mt-2 text-sm text-accent hover:underline" onclick={() => (expanded = !expanded)}>{expanded ? 'Less' : 'More'}</button>
          {/if}
        {:else}
          <p class="text-sm text-white/35">No description.</p>
        {/if}
      </section>

      {#if v.chapters?.length}
        <section>
          <h2 class="label mb-4">Chapters <span class="tabular ml-1 text-white/50">{v.chapters.length}</span></h2>
          <ol class="card divide-y divide-white/[0.05]">
            {#each v.chapters as ch, i}
              <li>
                <a href="/watch/{v.id}?t={Math.floor(ch.start)}" class="group flex items-center gap-4 px-5 py-3 text-sm transition-colors hover:bg-white/[0.02]">
                  <span class="tabular w-6 text-xs text-white/30">{String(i + 1).padStart(2, '0')}</span>
                  <span class="flex-1 truncate text-white/80 group-hover:text-white">{ch.title}</span>
                  <span class="tabular text-xs text-white/40 group-hover:text-accent">{clock(ch.start)}</span>
                </a>
              </li>
            {/each}
          </ol>
        </section>
      {/if}
    </div>

    <aside class="space-y-8">
      <section>
        <div class="mb-3 flex items-center justify-between">
          <h2 class="label">Tags</h2>
          <button
            class="text-xs text-white/40 hover:text-accent"
            onclick={() => {
              tags = [...v.tags]
              get('/tags').then((t) => (allTags = t.map((x) => x.name))).catch(() => {})
              editTags = true
            }}>Edit</button
          >
        </div>
        {#if v.tags.length}
          <div class="flex flex-wrap gap-1.5">
            {#each v.tags as t (t)}<a href="/library?tag={encodeURIComponent(t)}" class="chip">{t}</a>{/each}
          </div>
        {:else}
          <p class="text-sm text-white/35">No tags yet.</p>
        {/if}
      </section>

      {#if v.collections?.length}
        <section>
          <h2 class="label mb-3">In collections</h2>
          <div class="flex flex-wrap gap-1.5">
            {#each v.collections as c (c.id)}<a href="/collections/{c.id}" class="chip"><Icon name="layers" size={12} />{c.name}</a>{/each}
          </div>
        </section>
      {/if}

      <section>
        <h2 class="label mb-3">File</h2>
        <dl class="space-y-2.5 text-sm">
          <div class="flex justify-between gap-4"><dt class="text-white/40">Status</dt><dd class={v.status === 'ready' ? 'text-accent' : 'text-white/80'}>{v.status}</dd></div>
          {#if v.file_size}<div class="flex justify-between gap-4"><dt class="text-white/40">Size</dt><dd class="tabular text-white/80">{bytes(v.file_size)}</dd></div>{/if}
          <div class="flex justify-between gap-4"><dt class="text-white/40">Added</dt><dd class="text-white/80">{ago(v.added_at)}</dd></div>
          {#if v.playback.last_played_at}<div class="flex justify-between gap-4"><dt class="text-white/40">Last watched</dt><dd class="text-white/80">{ago(v.playback.last_played_at)}</dd></div>{/if}
          {#if v.storage_path}
            <div><dt class="text-white/40">On storage</dt><dd class="mt-1 font-mono text-xs break-all text-white/60">/library/{v.storage_path}</dd></div>
          {/if}
          <div class="pt-1"><a href={v.url} target="_blank" rel="noreferrer" class="inline-flex items-center gap-1.5 text-white/50 hover:text-accent">YouTube <Icon name="external" size={13} /></a></div>
        </dl>
      </section>
    </aside>
  </div>

  <!-- edit -->
  <Modal bind:open={editing} title="Edit" width="max-w-3xl">
    {#if form}
      <div class="space-y-6">
        <label class="block"><span class="label mb-2 block">Title</span><input class="field" bind:value={form.title} /></label>
        <label class="block"><span class="label mb-2 block">Description</span><textarea class="field min-h-28 leading-relaxed" bind:value={form.description}></textarea></label>
        <ClassifyFields bind:value={form} tagSuggestions={allTags} compact />
        {#if !v.classified}
          <p class="text-xs text-white/40">Choosing a category files this title out of Unsorted.</p>
        {/if}
      </div>
    {/if}
    {#snippet footer()}
      <button class="btn-quiet" onclick={() => (editing = false)}>Cancel</button>
      <button class="btn-primary" onclick={saveEdit} disabled={saving || !form?.title.trim()}>Save</button>
    {/snippet}
  </Modal>

  <Modal bind:open={editTags} title="Tags">
    <TagInput bind:tags suggestions={allTags} />
    {#snippet footer()}
      <button class="btn-quiet" onclick={() => (editTags = false)}>Cancel</button>
      <button class="btn-primary" onclick={async () => (await save({ tags }, 'Tags saved')) && (editTags = false)}>Save</button>
    {/snippet}
  </Modal>

  <Modal bind:open={confirmDelete} title="Delete “{v.title}”?">
    <p class="text-sm leading-relaxed text-white/65">The MP4, poster and subtitles are removed from the storage disk. This can't be undone.</p>
    {#snippet footer()}
      <button class="btn-quiet" onclick={() => (confirmDelete = false)}>Cancel</button>
      <button class="btn border border-white bg-white text-ink hover:bg-white/85" onclick={remove}>Delete</button>
    {/snippet}
  </Modal>

  <BulkModals bind:mode={collectionMode} ids={[v.id]} ondone={load} />
{/if}
