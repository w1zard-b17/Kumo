<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import FetchBar from '../components/FetchBar.svelte'
  import ClassifyFields from '../components/ClassifyFields.svelte'
  import Toggle from '../components/Toggle.svelte'
  import Rating from '../components/Rating.svelte'
  import Modal from '../components/Modal.svelte'
  import { get, post } from '../lib/api.js'
  import { app, draft, toast, fail, refreshJobs, categoryById } from '../lib/store.svelte.js'
  import { navigate, route } from '../lib/router.svelte.js'
  import { duration, bytes, LANGUAGES, langName } from '../lib/format.js'

  const s = app.settings || {}
  let preview = $state(draft.preview)
  let selected = $state([...draft.selected])
  let skip = $state(draft.skip || route.query.get('skip') === '1')

  let options = $state({
    quality: s.quality || '1080',
    subtitles: !!s.subtitles,
    sub_lang: s.sub_lang || 'en',
    auto_subs: s.auto_subs ?? true,
    audio_fallback: s.audio_fallback ?? true,
  })
  let cls = $state(freshClassification())
  let meta = $state(freshMeta())
  let step = $state(0)
  let submitting = $state(false)
  let warning = $state(null) // 409 from the disk-space check
  let knownTags = $state([])

  function freshClassification() {
    return {
      type: preview?.duration && preview.duration < 20 * 60 ? 'short' : 'documentary',
      category_id: null,
      subcategory: '',
      tags: [],
      year: preview?.year || null,
      language: (preview?.language || s.language || '').split('-')[0],
    }
  }
  function freshMeta() {
    return { title: preview?.title || '', description: preview?.description || '', rating: 0, watched: false }
  }

  const isPlaylist = $derived(preview?.kind === 'playlist')
  const steps = $derived(
    [isPlaylist && 'Select', 'Options', !skip && 'Classify', 'Details', 'Confirm'].filter(Boolean),
  )
  const current = $derived(steps[step])
  const items = $derived(
    !preview ? [] : isPlaylist ? preview.entries.filter((e) => selected.includes(e.youtube_id)) : [preview],
  )
  const estimate = $derived(isPlaylist ? null : preview?.estimates?.[options.quality] || null)
  const TITLES = {
    Select: 'Choose videos',
    Options: 'Download options',
    Classify: 'Classify',
    Details: 'Details',
    Confirm: 'Ready to download',
  }
  const canContinue = $derived.by(() => {
    if (current === 'Select') return selected.length > 0
    if (current === 'Classify') return !!cls.category_id
    if (current === 'Details' && !isPlaylist) return meta.title.trim().length > 0
    return true
  })
  const subLangs = $derived(
    preview && !isPlaylist ? [...new Set([...(preview.subtitles || []), ...(preview.auto_subtitles || []).map((l) => l.replace(/-orig$/, ''))])] : [],
  )

  onMount(async () => {
    try {
      knownTags = (await get('/tags')).map((t) => t.name)
    } catch {}
  })

  function onresult(p) {
    if (!p) return
    preview = draft.preview = p
    selected = p.kind === 'playlist' ? p.entries.filter((e) => !e.duplicate && !e.unavailable).map((e) => e.youtube_id) : [p.youtube_id]
    cls = freshClassification()
    meta = freshMeta()
    step = 0
  }

  function next() {
    if (!canContinue) return
    if (step < steps.length - 1) step++
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function submit(force = false) {
    submitting = true
    try {
      const body = {
        items: items.map((it) => ({
          youtube_id: it.youtube_id,
          url: it.url,
          title: isPlaylist ? it.title : meta.title.trim(),
          description: isPlaylist ? '' : meta.description,
          channel: it.channel || '',
          duration: it.duration || 0,
          thumbnail: it.thumbnail,
          year: it.year || null,
          size_estimate: isPlaylist ? null : estimate,
        })),
        options,
        classification: skip ? null : { ...cls, year: cls.year || null, category_id: cls.category_id },
        meta: { rating: meta.rating, watched: meta.watched },
        force,
      }
      const res = await post('/jobs', body)
      warning = null
      draft.preview = null
      draft.selected = []
      await refreshJobs()
      const n = res.jobs.length
      toast(n === 1 ? 'Download started' : `${n} downloads queued`, { kind: 'success' })
      if (res.skipped.length) toast(`${res.skipped.length} already in your library, skipped`)
      navigate('/downloads')
    } catch (e) {
      if (e.status === 409 && ['low_space', 'low_tmp', 'storage_unreachable', 'storage_offline'].includes(e.code)) warning = e
      else fail(e)
    } finally {
      submitting = false
    }
  }

  function toggleAll(on) {
    selected = on ? preview.entries.filter((e) => !e.duplicate && !e.unavailable).map((e) => e.youtube_id) : []
  }
</script>

{#if !preview}
  <div class="mx-auto max-w-2xl pt-10 text-center">
    <p class="label">Add to library</p>
    <h1 class="mt-3 text-2xl font-semibold tracking-tight">Start with a link</h1>
    <div class="mt-8 text-left"><FetchBar {onresult} autofocus /></div>
  </div>
{:else}
  <div class="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)] lg:gap-12">
    <!-- summary + steps -->
    <aside class="lg:sticky lg:top-10 lg:self-start">
      <button class="btn-quiet -ml-3 mb-5 !px-3" onclick={() => navigate('/')}><Icon name="arrow-left" size={16} /> Back</button>
      <div class="card overflow-hidden">
        <div class="relative aspect-video bg-char">
          {#if preview.thumbnail}<img src={preview.thumbnail} alt="" class="size-full object-cover" />{/if}
          {#if isPlaylist}
            <span class="absolute right-3 bottom-3 inline-flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-0.5 text-xs">
              <Icon name="queue" size={13} /> {preview.entries.length}
            </span>
          {:else if preview.duration}
            <span class="tabular absolute right-3 bottom-3 rounded-md bg-black/75 px-2 py-0.5 text-xs">{duration(preview.duration)}</span>
          {/if}
        </div>
        <div class="p-4">
          <p class="line-clamp-2 text-sm leading-snug font-medium">{isPlaylist ? preview.title : meta.title || preview.title}</p>
          <p class="mt-1 truncate text-xs text-white/40">{preview.channel}</p>
        </div>
      </div>

      <ol class="mt-6 hidden space-y-1 lg:block">
        {#each steps as name, i (name)}
          <li>
            <button
              class="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm transition-colors
                     {i === step ? 'text-white' : i < step ? 'text-white/60 hover:text-white' : 'text-white/25'}"
              disabled={i > step}
              onclick={() => (step = i)}
            >
              <span
                class="tabular grid size-6 place-items-center rounded-full border text-[11px]
                       {i === step ? 'border-accent text-accent' : i < step ? 'border-accent bg-accent text-ink' : 'border-white/15'}"
              >
                {#if i < step}<Icon name="check" size={12} stroke={2.5} />{:else}{i + 1}{/if}
              </span>
              {name}
            </button>
          </li>
        {/each}
      </ol>
    </aside>

    <!-- step body -->
    <section class="min-w-0">
      <div class="mb-7 flex items-baseline justify-between gap-4">
        <div>
          <p class="label">Step {step + 1} of {steps.length}</p>
          <h1 class="mt-2 text-2xl font-semibold tracking-tight">
            {TITLES[current]}
          </h1>
        </div>
        {#if current === 'Classify'}
          <button class="btn-quiet text-xs" onclick={() => { skip = true; step = steps.indexOf('Details') }}>Skip, classify later</button>
        {/if}
      </div>

      {#key current}
        <div class="rise">
          {#if current === 'Select'}
            <div class="mb-3 flex items-center justify-between text-sm">
              <span class="text-white/50"><span class="tabular text-white">{selected.length}</span> of {preview.entries.length} selected</span>
              <div class="flex gap-1">
                <button class="btn-quiet !py-1 text-xs" onclick={() => toggleAll(true)}>All</button>
                <button class="btn-quiet !py-1 text-xs" onclick={() => toggleAll(false)}>None</button>
              </div>
            </div>
            <ul class="card divide-y divide-white/[0.05]">
              {#each preview.entries as e (e.youtube_id)}
                {@const disabled = !!e.duplicate || e.unavailable}
                {@const on = selected.includes(e.youtube_id)}
                <li>
                  <label class="flex items-center gap-4 px-4 py-3 {disabled ? 'opacity-40' : 'cursor-pointer hover:bg-white/[0.02]'}">
                    <input
                      type="checkbox"
                      class="size-4 accent-[#2be080]"
                      checked={on}
                      {disabled}
                      onchange={() => (selected = on ? selected.filter((x) => x !== e.youtube_id) : [...selected, e.youtube_id])}
                    />
                    <img src={e.thumbnail} alt="" loading="lazy" class="aspect-video w-24 shrink-0 rounded-md bg-char object-cover" />
                    <span class="min-w-0 flex-1">
                      <span class="line-clamp-1 text-sm">{e.title}</span>
                      <span class="mt-0.5 block text-xs text-white/40">
                        {e.duplicate ? 'Already in library' : e.unavailable ? 'Unavailable' : duration(e.duration)}
                      </span>
                    </span>
                  </label>
                </li>
              {/each}
            </ul>
          {:else if current === 'Options'}
            <div class="space-y-8">
              <div>
                <p class="label mb-3">Quality</p>
                <div class="grid gap-2 sm:grid-cols-3">
                  {#each [['720', '720p', 'Smaller files'], ['1080', '1080p', 'Recommended'], ['best', 'Best', 'Highest available']] as [q, name, hint] (q)}
                    {@const e = preview.estimates?.[q]}
                    <button
                      aria-pressed={options.quality === q}
                      onclick={() => (options.quality = q)}
                      class="rounded-xl border p-4 text-left transition-all
                             {options.quality === q ? 'border-accent/70 bg-accent/[0.07]' : 'border-white/[0.08] hover:border-white/20'}"
                    >
                      <span class="flex items-center justify-between">
                        <span class="text-base font-semibold {options.quality === q ? 'text-white' : 'text-white/80'}">{name}</span>
                        {#if options.quality === q}<span class="text-accent"><Icon name="check" size={16} stroke={2.2} /></span>{/if}
                      </span>
                      <span class="mt-1 block text-xs text-white/40">{hint}</span>
                      {#if !isPlaylist && e}<span class="tabular mt-3 block text-xs text-white/60">~{bytes(e)}</span>{/if}
                    </button>
                  {/each}
                </div>
                {#if options.quality === 'best'}
                  <p class="mt-3 text-xs text-white/40">Best may pick VP9/AV1 video; very old devices can struggle to play it.</p>
                {/if}
              </div>

              <div class="card divide-y divide-white/[0.05] px-5">
                <div class="py-4"><Toggle bind:checked={options.subtitles} label="Subtitles" hint="Saved next to the video as WebVTT" /></div>
                {#if options.subtitles}
                  <div class="flex items-center justify-between gap-6 py-4">
                    <span class="text-sm text-white/90">Language</span>
                    <select class="field !w-44" bind:value={options.sub_lang}>
                      {#each LANGUAGES.filter(([c]) => c) as [code, name]}
                        <option value={code}>{name}{subLangs.length && !subLangs.includes(code) ? ' (n/a)' : ''}</option>
                      {/each}
                    </select>
                  </div>
                  <div class="py-4"><Toggle bind:checked={options.auto_subs} label="Use auto-generated captions" hint="When there are no uploaded subtitles" /></div>
                {/if}
                <div class="py-4">
                  <Toggle bind:checked={options.audio_fallback} label="Audio-only fallback" hint="Keep the audio if no video format can be downloaded" />
                </div>
              </div>
            </div>
          {:else if current === 'Classify'}
            <ClassifyFields bind:value={cls} tagSuggestions={[...new Set([...(preview.tags || []), ...knownTags])]} />
          {:else if current === 'Details'}
            <div class="space-y-6">
              {#if !isPlaylist}
                <label class="block">
                  <span class="label mb-2 block">Title</span>
                  <input class="field !py-3 !text-base" bind:value={meta.title} maxlength="300" />
                </label>
                <label class="block">
                  <span class="label mb-2 block">Description</span>
                  <textarea class="field min-h-36 resize-y leading-relaxed" bind:value={meta.description}></textarea>
                </label>
              {/if}
              <div class="card divide-y divide-white/[0.05] px-5">
                <div class="flex items-center justify-between gap-6 py-4">
                  <span class="text-sm text-white/90">Rating</span>
                  <Rating bind:value={meta.rating} />
                </div>
                <div class="py-4"><Toggle bind:checked={meta.watched} label="Already watched" /></div>
              </div>
              {#if !isPlaylist}
                <p class="text-xs text-white/40">The poster is the YouTube thumbnail. It's saved next to the video on the storage disk.</p>
              {/if}
            </div>
          {:else if current === 'Confirm'}
            {@const cat = categoryById(cls.category_id)}
            <dl class="card divide-y divide-white/[0.05] text-sm">
              {#each [
                ['What', isPlaylist ? `${items.length} video${items.length === 1 ? '' : 's'} from “${preview.title}”` : meta.title],
                ['Quality', options.quality === 'best' ? 'Best available' : `${options.quality}p`],
                ['Subtitles', options.subtitles ? `${langName(options.sub_lang)}${options.auto_subs ? ', auto captions allowed' : ''}` : 'None'],
                ['Filed under', skip ? 'Unsorted, classify later' : `${app.types[cls.type]} · ${cat?.name}${cls.subcategory ? ` · ${cls.subcategory}` : ''}`],
                ['Tags', !skip && cls.tags.length ? cls.tags.join(', ') : '—'],
                ['Year · language', [cls.year, langName(cls.language)].filter(Boolean).join(' · ') || '—'],
                ['Size', estimate ? `~${bytes(estimate)}` : 'Unknown until download'],
              ] as [k, v]}
                <div class="grid grid-cols-[130px_1fr] gap-4 px-5 py-3.5">
                  <dt class="text-white/40">{k}</dt>
                  <dd class="min-w-0 break-words text-white/90">{v}</dd>
                </div>
              {/each}
            </dl>
            <p class="mt-4 text-xs leading-relaxed text-white/40">
              yt-dlp downloads into the VM's temp folder, ffmpeg remuxes to MP4, then the file moves to
              <span class="font-mono text-white/60">/library/{skip ? 'Unsorted' : cat?.name}/</span> on the storage host.
            </p>
          {/if}
        </div>
      {/key}

      <div class="mt-10 flex items-center justify-between gap-3 border-t border-white/[0.06] pt-6">
        <button class="btn-quiet" onclick={() => (step > 0 ? step-- : navigate('/'))}>
          <Icon name="arrow-left" size={16} /> {step > 0 ? 'Back' : 'Cancel'}
        </button>
        {#if current === 'Confirm'}
          <button class="btn-primary h-11 px-6" onclick={() => submit(false)} disabled={submitting}>
            {#if submitting}<span class="size-4 animate-spin rounded-full border-2 border-ink/30 border-t-ink"></span>{:else}<Icon name="download" size={17} stroke={2} />{/if}
            Start download
          </button>
        {:else}
          <button class="btn-primary h-11 px-6" onclick={next} disabled={!canContinue}>
            Continue <Icon name="arrow-right" size={16} stroke={2} />
          </button>
        {/if}
      </div>
    </section>
  </div>
{/if}

<Modal open={!!warning} title="Download anyway?" onclose={() => (warning = null)}>
  <p class="text-sm leading-relaxed text-white/70">{warning?.message}</p>
  {#if warning?.data?.needed}
    <p class="tabular mt-3 text-sm text-white/50">
      Needs ~{bytes(warning.data.needed)}, {bytes(warning.data.available)} available.
    </p>
  {/if}
  {#snippet footer()}
    <button class="btn-quiet" onclick={() => (warning = null)}>Cancel</button>
    <button class="btn-primary" onclick={() => submit(true)} disabled={submitting}>Download anyway</button>
  {/snippet}
</Modal>
