<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import FetchBar from '../components/FetchBar.svelte'
  import PreviewCard from '../components/PreviewCard.svelte'
  import VideoCard from '../components/VideoCard.svelte'
  import JobRow from '../components/JobRow.svelte'
  import Rail from '../components/Rail.svelte'
  import { get } from '../lib/api.js'
  import { app, draft, fail, onJobsFinished } from '../lib/store.svelte.js'
  import { navigate } from '../lib/router.svelte.js'
  import { duration, bytes } from '../lib/format.js'

  let data = $state(null)
  let preview = $state(draft.preview)
  let bar = $state()

  async function load() {
    try {
      data = await get('/home')
    } catch (e) {
      fail(e)
    }
  }

  onMount(() => {
    load()
    return onJobsFinished(load)
  })

  function onresult(p) {
    preview = p
    if (p?.kind === 'playlist') {
      draft.preview = p
      draft.selected = p.entries.filter((e) => !e.duplicate && !e.unavailable).map((e) => e.youtube_id)
      draft.skip = false
      navigate('/add')
    }
  }

  function start(skip) {
    draft.preview = preview
    draft.selected = [preview.youtube_id]
    draft.skip = skip
    navigate(skip ? '/add?skip=1' : '/add')
  }

  const hour = new Date().getHours()
  const greeting = hour < 5 ? 'Late night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const empty = $derived(data && !data.recent.length && !data.active.length)
</script>

<div class="space-y-14">
  <section class="mx-auto max-w-3xl pt-4 text-center md:pt-12">
    <p class="label">{greeting}</p>
    <h1 class="mt-3 text-3xl font-semibold tracking-[-0.03em] text-white md:text-[44px] md:leading-[1.1]">
      What will you learn <span class="text-accent">tonight</span>?
    </h1>
    <div class="mt-9 text-left">
      <FetchBar bind:this={bar} {onresult} autofocus />
    </div>
    {#if !preview}
      <p class="mt-4 text-xs text-white/35">
        A video, a youtu.be short link or a playlist. Press <kbd class="rounded border border-white/15 px-1 font-mono text-[10px] text-white/55">Enter</kbd> to fetch.
      </p>
    {/if}
  </section>

  {#if preview?.kind === 'video'}
    <div class="mx-auto max-w-5xl">
      <PreviewCard
        {preview}
        onadd={() => start(false)}
        onskip={() => start(true)}
        onplaylist={() => bar.fetchUrl(`https://www.youtube.com/playlist?list=${preview.in_playlist}`, true)}
        onclose={() => (preview = draft.preview = null)}
      />
    </div>
  {/if}

  {#if data?.active.length}
    <Rail title="Downloading" href="/downloads">
      <div class="card divide-y divide-white/[0.05] px-4">
        {#each data.active.slice(0, 3) as job (job.id)}
          {@const live = app.active.find((j) => j.id === job.id) || job}
          <JobRow job={live} compact />
        {/each}
      </div>
    </Rail>
  {/if}

  {#if data?.continue.length}
    <Rail title="Continue watching">
      <div class="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 scrollbar-none sm:-mx-6 sm:px-6 md:mx-0 md:grid md:grid-cols-3 md:overflow-visible md:px-0 xl:grid-cols-4">
        {#each data.continue as v (v.id)}
          <div class="w-64 shrink-0 snap-start md:w-auto">
            <VideoCard video={v} href="/watch/{v.id}" />
          </div>
        {/each}
      </div>
    </Rail>
  {/if}

  {#if data?.recent.length}
    <Rail title="Recently added" href="/library">
      <div class="grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
        {#each data.recent as v (v.id)}
          <VideoCard video={v} size="sm" />
        {/each}
      </div>
    </Rail>
  {/if}

  {#if data && data.stats.videos}
    <section class="flex flex-wrap items-center justify-center gap-x-10 gap-y-3 border-t border-white/[0.06] pt-8 text-center">
      <div><p class="tabular text-lg font-semibold">{data.stats.videos}</p><p class="label mt-1">Titles</p></div>
      <div><p class="tabular text-lg font-semibold">{duration(data.stats.seconds)}</p><p class="label mt-1">Runtime</p></div>
      <div><p class="tabular text-lg font-semibold">{bytes(data.stats.bytes)}</p><p class="label mt-1">On disk</p></div>
      {#if data.stats.unsorted}
        <a href="/library?unsorted=1" class="group">
          <p class="tabular text-lg font-semibold text-accent">{data.stats.unsorted}</p>
          <p class="label mt-1 group-hover:text-white/70">Unsorted</p>
        </a>
      {/if}
    </section>
  {/if}

  {#if empty && !preview}
    <section class="rise mx-auto max-w-lg pt-4 text-center">
      <div class="mx-auto grid max-w-sm grid-cols-3 gap-3 text-left text-xs text-white/45">
        {#each [['link', 'Paste', 'a YouTube link'], ['tag', 'Classify', 'type & category'], ['play', 'Watch', 'from your library']] as [icon, a, b], i}
          <div class="card p-4">
            <span class="text-accent"><Icon name={icon} size={18} /></span>
            <p class="mt-3 font-medium text-white/85">{i + 1}. {a}</p>
            <p class="mt-0.5">{b}</p>
          </div>
        {/each}
      </div>
    </section>
  {/if}
</div>
