<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import VideoCard from '../components/VideoCard.svelte'
  import Empty from '../components/Empty.svelte'
  import Modal from '../components/Modal.svelte'
  import { get, patch, del } from '../lib/api.js'
  import { fail, toast } from '../lib/store.svelte.js'
  import { navigate, back } from '../lib/router.svelte.js'
  import { duration } from '../lib/format.js'

  let { params } = $props()
  let c = $state(null)
  let items = $state([])
  let editing = $state(false)
  let confirmDelete = $state(false)
  let form = $state({ name: '', description: '' })

  async function load() {
    try {
      const [col, vids] = await Promise.all([
        get(`/collections/${params.id}`),
        get('/videos', { collection: params.id, sort: 'title', order: 'asc', limit: 1000 }),
      ])
      c = col
      items = vids.items
    } catch (e) {
      fail(e)
      if (e.status === 404) navigate('/collections', { replace: true })
    }
  }

  onMount(load)

  const runtime = $derived(items.reduce((s, v) => s + (v.duration || 0), 0))
  const watched = $derived(items.filter((v) => v.playback.watched).length)

  async function save() {
    try {
      c = await patch(`/collections/${c.id}`, { name: form.name.trim(), description: form.description })
      editing = false
    } catch (e) {
      fail(e)
    }
  }

  async function removeItem(v) {
    try {
      c = await del(`/collections/${c.id}/videos/${v.id}`)
      items = items.filter((x) => x.id !== v.id)
      toast(`Removed “${v.title}”`)
    } catch (e) {
      fail(e)
    }
  }

  async function remove() {
    try {
      await del(`/collections/${c.id}`)
      toast(`Deleted “${c.name}”`)
      navigate('/collections', { replace: true })
    } catch (e) {
      fail(e)
    }
  }
</script>

{#if c}
  <button class="btn-quiet -ml-3 mb-6 !px-3" onclick={() => back('/collections')}><Icon name="arrow-left" size={16} /> Collections</button>
  <header class="mb-10 flex flex-wrap items-end justify-between gap-6">
    <div class="min-w-0">
      <p class="label tabular">{items.length} title{items.length === 1 ? '' : 's'} · {duration(runtime)} · {watched} watched</p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">{c.name}</h1>
      {#if c.description}<p class="mt-2 max-w-2xl text-sm text-white/55">{c.description}</p>{/if}
    </div>
    <div class="flex gap-2">
      {#if items.length}
        {@const first = items.find((v) => !v.playback.watched) || items[0]}
        <a href="/watch/{first.id}" class="btn-primary"><Icon name="play" size={15} /> Play</a>
      {/if}
      <button
        class="btn-icon size-10 border border-white/12"
        onclick={() => {
          form = { name: c.name, description: c.description }
          editing = true
        }}
        aria-label="Edit collection"><Icon name="edit" size={16} /></button
      >
      <button class="btn-icon size-10 border border-white/12" onclick={() => (confirmDelete = true)} aria-label="Delete collection"><Icon name="trash" size={16} /></button>
    </div>
  </header>

  {#if items.length}
    <div class="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
      {#each items as v (v.id)}
        <div class="group/item relative">
          <VideoCard video={v} />
          <button
            class="absolute top-2 right-2 grid size-7 place-items-center rounded-full bg-black/75 text-white/70 opacity-0 transition-opacity group-hover/item:opacity-100 hover:text-white"
            onclick={() => removeItem(v)}
            aria-label="Remove from collection"
            title="Remove from collection"><Icon name="x" size={14} /></button
          >
        </div>
      {/each}
    </div>
  {:else}
    <Empty icon="layers" title="Empty collection" text="Add titles from the library (Select → Collection) or from a title's page.">
      <a href="/library" class="btn-ghost">Open library</a>
    </Empty>
  {/if}

  <Modal bind:open={editing} title="Edit collection">
    <div class="space-y-4">
      <label class="block"><span class="label mb-2 block">Name</span><input class="field" bind:value={form.name} maxlength="60" /></label>
      <label class="block"><span class="label mb-2 block">Description</span><input class="field" bind:value={form.description} maxlength="500" /></label>
    </div>
    {#snippet footer()}
      <button class="btn-quiet" onclick={() => (editing = false)}>Cancel</button>
      <button class="btn-primary" onclick={save} disabled={!form.name.trim()}>Save</button>
    {/snippet}
  </Modal>

  <Modal bind:open={confirmDelete} title="Delete “{c.name}”?">
    <p class="text-sm text-white/65">The collection is removed. The titles stay in your library.</p>
    {#snippet footer()}
      <button class="btn-quiet" onclick={() => (confirmDelete = false)}>Cancel</button>
      <button class="btn border border-white bg-white text-ink hover:bg-white/85" onclick={remove}>Delete</button>
    {/snippet}
  </Modal>
{/if}
