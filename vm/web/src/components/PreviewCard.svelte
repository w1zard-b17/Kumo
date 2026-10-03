<script>
  import Icon from './Icon.svelte'
  import { duration, bytes } from '../lib/format.js'

  let { preview, onadd, onskip, onplaylist, onclose } = $props()

  const est = $derived(preview.estimates || {})
  const top = $derived(preview.heights?.length ? preview.heights[preview.heights.length - 1] : null)
</script>

<article class="rise card overflow-hidden">
  <div class="grid gap-0 md:grid-cols-[minmax(0,420px)_1fr]">
    <div class="relative aspect-video bg-char md:aspect-auto md:min-h-full">
      {#if preview.thumbnail}
        <img src={preview.thumbnail} alt="" class="absolute inset-0 size-full object-cover" />
      {/if}
      {#if preview.duration}
        <span class="tabular absolute right-3 bottom-3 rounded-md bg-black/75 px-2 py-0.5 text-xs font-medium">{duration(preview.duration)}</span>
      {/if}
    </div>

    <div class="flex min-w-0 flex-col p-6 md:p-7">
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0">
          <p class="label">{preview.channel}</p>
          <h2 class="mt-2 text-xl leading-snug font-semibold tracking-tight text-white md:text-2xl">{preview.title}</h2>
        </div>
        <button class="btn-icon -mt-1 -mr-2 shrink-0" onclick={onclose} aria-label="Clear"><Icon name="x" /></button>
      </div>

      <dl class="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {#if preview.year}<div><dt class="sr-only">Year</dt><dd class="text-white/60">{preview.year}</dd></div>{/if}
        {#if top}<div><dt class="sr-only">Max quality</dt><dd class="text-white/60">up to {top}p</dd></div>{/if}
        {#if est['1080'] || est.best}
          <div><dt class="sr-only">Size</dt><dd class="tabular text-white/60">~{bytes(est['1080'] || est.best)}</dd></div>
        {/if}
        {#if preview.chapters?.length}<div><dd class="text-white/60">{preview.chapters.length} chapters</dd></div>{/if}
        {#if preview.subtitles?.length}<div><dd class="text-white/60">Subtitles: {preview.subtitles.slice(0, 4).join(', ')}{preview.subtitles.length > 4 ? '…' : ''}</dd></div>{/if}
      </dl>

      {#if preview.duplicate}
        <p class="mt-5 flex items-center gap-2 rounded-xl border border-white/10 px-3.5 py-2.5 text-sm text-white/80">
          <Icon name="check" size={16} class="text-accent" />
          Already in your library.
          <a class="ml-auto text-accent hover:underline" href="/v/{preview.duplicate.id}">Open</a>
        </p>
      {:else}
        {#if preview.age_limit >= 18}
          <p class="mt-5 flex items-center gap-2 text-sm text-white/70"><Icon name="alert" size={15} /> Age-restricted, so the download may fail.</p>
        {/if}
        <div class="mt-auto flex flex-wrap items-center gap-2 pt-6">
          <button class="btn-primary h-11 px-5" onclick={onadd}>Classify & download <Icon name="arrow-right" size={16} stroke={2} /></button>
          <button class="btn-quiet h-11" onclick={onskip}>Skip, classify later</button>
          {#if preview.in_playlist}
            <button class="btn-quiet h-11" onclick={onplaylist}><Icon name="queue" size={16} /> Open whole playlist</button>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</article>
