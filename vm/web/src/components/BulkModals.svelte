<script>
  // Reclassify / add tags / add to collection for one or many videos.
  import Modal from './Modal.svelte'
  import ClassifyFields from './ClassifyFields.svelte'
  import TagInput from './TagInput.svelte'
  import Icon from './Icon.svelte'
  import { get, post } from '../lib/api.js'
  import { fail, toast, loadCategories } from '../lib/store.svelte.js'

  let { mode = $bindable(null), ids = [], ondone } = $props()

  let cls = $state({ type: 'documentary', category_id: null, subcategory: '', tags: [], year: null, language: '' })
  let tags = $state([])
  let collections = $state([])
  let newName = $state('')
  let busy = $state(false)

  $effect(() => {
    if (mode === 'collection') get('/collections').then((c) => (collections = c)).catch(fail)
    if (mode) {
      tags = []
      newName = ''
    }
  })

  async function run(body) {
    busy = true
    try {
      const r = await post('/videos/bulk', { ids, ...body })
      if (r.errors.length) toast(`${r.errors.length} failed: ${r.errors[0].error}`, { kind: 'error' })
      else toast(`Updated ${r.done} title${r.done === 1 ? '' : 's'}`, { kind: 'success' })
      mode = null
      loadCategories()
      ondone?.()
    } catch (e) {
      fail(e)
    } finally {
      busy = false
    }
  }

  async function toCollection(id) {
    await run({ action: 'add_to_collection', collection_id: id })
  }

  async function createAndAdd() {
    if (!newName.trim()) return
    try {
      const c = await post('/collections', { name: newName.trim() })
      await toCollection(c.id)
    } catch (e) {
      fail(e)
    }
  }
</script>

<Modal open={mode === 'reclassify'} title="Reclassify {ids.length} title{ids.length === 1 ? '' : 's'}" width="max-w-3xl" onclose={() => (mode = null)}>
  <ClassifyFields bind:value={cls} compact showOptional={false} />
  <p class="mt-5 text-xs text-white/40">Files move to the new category folder on the storage host.</p>
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (mode = null)}>Cancel</button>
    <button class="btn-primary" disabled={!cls.category_id || busy} onclick={() => run({ action: 'reclassify', type: cls.type, category_id: cls.category_id })}>
      Apply
    </button>
  {/snippet}
</Modal>

<Modal open={mode === 'tags'} title="Add tags" onclose={() => (mode = null)}>
  <TagInput bind:tags />
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (mode = null)}>Cancel</button>
    <button class="btn-primary" disabled={!tags.length || busy} onclick={() => run({ action: 'add_tags', tags })}>Add tags</button>
  {/snippet}
</Modal>

<Modal open={mode === 'collection'} title="Add to collection" onclose={() => (mode = null)}>
  <div class="space-y-1">
    {#each collections as c (c.id)}
      <button
        class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm hover:bg-white/[0.04]"
        disabled={busy}
        onclick={() => toCollection(c.id)}
      >
        <span class="flex items-center gap-3"><Icon name="layers" size={16} class="text-white/40" />{c.name}</span>
        <span class="tabular text-xs text-white/35">{c.count}</span>
      </button>
    {/each}
  </div>
  <form
    class="mt-4 flex gap-2"
    onsubmit={(e) => {
      e.preventDefault()
      createAndAdd()
    }}
  >
    <input class="field" bind:value={newName} placeholder="New collection…" />
    <button class="btn-ghost shrink-0" disabled={!newName.trim() || busy}><Icon name="plus" size={15} /> Create</button>
  </form>
</Modal>
