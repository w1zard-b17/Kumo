<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import JobRow from '../components/JobRow.svelte'
  import Empty from '../components/Empty.svelte'
  import { get, del } from '../lib/api.js'
  import { app, refreshJobs, onJobsFinished, fail, toast } from '../lib/store.svelte.js'
  import { bytes } from '../lib/format.js'

  let history = $state([])
  let filter = $state('all')
  let loaded = $state(false)

  async function loadHistory() {
    try {
      history = await get('/jobs', { state: 'history', limit: 300 })
    } catch (e) {
      fail(e)
    }
    loaded = true
  }

  onMount(() => {
    refreshJobs()
    loadHistory()
    return onJobsFinished(loadHistory)
  })

  const shown = $derived(history.filter((j) => filter === 'all' || j.status === filter))
  const counts = $derived({
    done: history.filter((j) => j.status === 'done').length,
    failed: history.filter((j) => j.status === 'failed').length,
    canceled: history.filter((j) => j.status === 'canceled').length,
  })

  async function clear() {
    try {
      const r = await del('/jobs')
      toast(`Cleared ${r.deleted} entr${r.deleted === 1 ? 'y' : 'ies'}`)
      loadHistory()
    } catch (e) {
      fail(e)
    }
  }
</script>

<header class="mb-10 flex flex-wrap items-end justify-between gap-4">
  <div>
    <p class="label">Queue</p>
    <h1 class="mt-2 text-3xl font-semibold tracking-tight">Downloads</h1>
  </div>
  {#if app.storage?.reachable}
    <p class="tabular text-sm text-white/45">
      <span class="mr-1.5 inline-block size-1.5 rounded-full {app.storage.online ? 'bg-accent' : 'border border-white/60'}"></span>
      {app.storage.online ? `${bytes(app.storage.available)} free on ${app.storage.disk}` : 'Storage disk offline'}
    </p>
  {/if}
</header>

<section>
  <h2 class="label mb-3">Active <span class="tabular ml-1 text-white/60">{app.active.length || ''}</span></h2>
  {#if app.active.length}
    <div class="card divide-y divide-white/[0.05] px-5">
      {#each app.active as job (job.id)}
        <JobRow {job} onchange={loadHistory} />
      {/each}
    </div>
  {:else}
    <div class="card flex items-center gap-3 px-5 py-6 text-sm text-white/45">
      <Icon name="check" size={16} class="text-accent" /> Nothing downloading.
      <a href="/add" class="ml-auto text-accent hover:underline">Add a link</a>
    </div>
  {/if}
</section>

<section class="mt-14">
  <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
    <h2 class="label">History</h2>
    <div class="flex items-center gap-2">
      <div class="seg">
        {#each [['all', 'All'], ['done', `Done ${counts.done || ''}`], ['failed', `Failed ${counts.failed || ''}`], ['canceled', 'Canceled']] as [k, label] (k)}
          <button aria-pressed={filter === k} onclick={() => (filter = k)}>{label}</button>
        {/each}
      </div>
      {#if history.length}
        <button class="btn-quiet !py-1.5 text-xs" onclick={clear}><Icon name="trash" size={14} /> Clear</button>
      {/if}
    </div>
  </div>
  {#if shown.length}
    <div class="card divide-y divide-white/[0.05] px-5">
      {#each shown as job (job.id)}
        <JobRow {job} onchange={loadHistory} />
      {/each}
    </div>
  {:else if loaded}
    <Empty icon="download" title="No history yet" text="Finished, failed and canceled downloads show up here." />
  {/if}
</section>
