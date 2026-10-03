<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import Empty from '../components/Empty.svelte'
  import Modal from '../components/Modal.svelte'
  import { get, post } from '../lib/api.js'
  import { fail, toast } from '../lib/store.svelte.js'
  import { navigate } from '../lib/router.svelte.js'

  let list = $state(null)
  let creating = $state(false)
  let name = $state('')
  let description = $state('')

  onMount(async () => {
    try {
      list = await get('/collections')
    } catch (e) {
      fail(e)
      list = []
    }
  })

  async function create() {
    try {
      const c = await post('/collections', { name: name.trim(), description })
      toast(`Created “${c.name}”`, { kind: 'success' })
      creating = false
      navigate(`/collections/${c.id}`)
    } catch (e) {
      fail(e)
    }
  }
</script>

<header class="mb-10 flex flex-wrap items-end justify-between gap-4">
  <div>
    <p class="label">Your lists</p>
    <h1 class="mt-2 text-3xl font-semibold tracking-tight">Collections</h1>
  </div>
  <button
    class="btn-ghost"
    onclick={() => {
      name = ''
      description = ''
      creating = true
    }}><Icon name="plus" size={16} /> New collection</button
  >
</header>

{#if list && !list.length}
  <Empty icon="layers" title="No collections yet" text="Group titles into lists like “Space”, “Cold War” or “To watch this weekend”.">
    <button class="btn-primary" onclick={() => (creating = true)}><Icon name="plus" size={16} /> New collection</button>
  </Empty>
{:else if list}
  <div class="grid grid-cols-1 gap-x-5 gap-y-9 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
    {#each list as c (c.id)}
      {@const n = c.posters.length}
      <a href="/collections/{c.id}" class="group rise block">
        <div
          class="grid aspect-video gap-0.5 overflow-hidden rounded-xl bg-char ring-1 ring-white/[0.06] transition-all duration-300 group-hover:ring-white/20
                 {n <= 1 ? 'grid-cols-1' : n === 2 ? 'grid-cols-2' : 'grid-cols-2 grid-rows-2'}"
        >
          {#if !n}
            <div class="grid place-items-center bg-coal text-white/15"><Icon name="layers" size={24} /></div>
          {/if}
          {#each c.posters.slice(0, n === 3 ? 3 : 4) as src, i}
            <img
              {src}
              alt=""
              loading="lazy"
              class="size-full object-cover brightness-90 transition-all duration-500 group-hover:brightness-100 {n === 3 && i === 0 ? 'row-span-2' : ''}"
            />
          {/each}
        </div>
        <div class="mt-3 flex items-baseline justify-between gap-3 px-0.5">
          <h3 class="truncate font-medium text-white/95 transition-colors group-hover:text-accent">{c.name}</h3>
          <span class="tabular shrink-0 text-xs text-white/40">{c.count} title{c.count === 1 ? '' : 's'}</span>
        </div>
        {#if c.description}<p class="mt-1 line-clamp-1 px-0.5 text-xs text-white/40">{c.description}</p>{/if}
      </a>
    {/each}
  </div>
{/if}

<Modal bind:open={creating} title="New collection">
  <form
    id="new-collection"
    class="space-y-4"
    onsubmit={(e) => {
      e.preventDefault()
      name.trim() && create()
    }}
  >
    <label class="block"><span class="label mb-2 block">Name</span><input class="field" bind:value={name} placeholder="e.g. Space" maxlength="60" /></label>
    <label class="block"><span class="label mb-2 block">Description</span><input class="field" bind:value={description} placeholder="Optional" maxlength="500" /></label>
  </form>
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (creating = false)}>Cancel</button>
    <button class="btn-primary" form="new-collection" type="submit" disabled={!name.trim()}>Create</button>
  {/snippet}
</Modal>
