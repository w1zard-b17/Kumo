<script>
  import Icon from './Icon.svelte'
  import { duration, pct } from '../lib/format.js'

  let {
    video,
    selectable = false,
    selected = false,
    onselect,
    showProgress = true,
    size = 'md',
    href = null,
  } = $props()

  const progress = $derived(
    video.playback && !video.playback.watched ? pct(video.playback.position, video.playback.duration || video.duration) : 0,
  )
  const target = $derived(href ?? `/v/${video.id}`)

  function click(e) {
    if (selectable) {
      e.preventDefault()
      onselect?.(video)
    }
  }
</script>

<a
  href={target}
  onclick={click}
  class="group block min-w-0 rounded-2xl outline-offset-4"
>
  {#if selectable}<span class="sr-only">{selected ? 'Selected: ' : 'Select: '}</span>{/if}
  <div
    class="relative aspect-video overflow-hidden rounded-xl bg-char ring-1 transition-all duration-300
           {selected ? 'ring-2 ring-accent' : 'ring-white/[0.06] group-hover:ring-white/20'}"
  >
    <!-- shimmer sits behind the poster until it loads -->
    <div class="skeleton absolute inset-0"></div>
    <img
      src={video.poster}
      alt=""
      loading="lazy"
      decoding="async"
      class="relative size-full object-cover transition-all duration-500 ease-out group-hover:scale-[1.03]
             {video.playback?.watched ? 'brightness-[0.55]' : 'brightness-90 group-hover:brightness-100'}"
    />

    <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>

    {#if video.duration}
      <span class="tabular absolute right-2 bottom-2 rounded-md bg-black/75 px-1.5 py-0.5 text-[11px] font-medium text-white/90">
        {duration(video.duration)}
      </span>
    {/if}

    {#if video.playback?.watched}
      <span class="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/70 px-2 py-0.5 text-[10.5px] font-medium text-accent">
        <Icon name="check" size={12} stroke={2.2} /> Watched
      </span>
    {:else if !video.classified}
      <span class="absolute top-2 left-2 rounded-full bg-black/70 px-2 py-0.5 text-[10.5px] font-medium text-white/80">
        Unsorted
      </span>
    {/if}

    {#if selectable}
      <span
        class="absolute top-2 right-2 grid size-6 place-items-center rounded-full border-2 transition-colors
               {selected ? 'border-accent bg-accent text-ink' : 'border-white/70 bg-black/40 text-transparent'}"
      >
        <Icon name="check" size={13} stroke={2.6} />
      </span>
    {:else}
      <span
        class="absolute inset-0 m-auto grid size-12 translate-y-1 place-items-center rounded-full bg-accent text-ink opacity-0 shadow-lg shadow-black/40 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100"
      >
        <Icon name="play" size={20} />
      </span>
    {/if}

    {#if showProgress && progress > 0}
      <div class="absolute inset-x-0 bottom-0 h-[3px] bg-white/15">
        <div class="h-full bg-accent" style="width:{progress}%"></div>
      </div>
    {/if}
  </div>

  <div class="mt-2.5 px-0.5">
    <h3 class="line-clamp-2 leading-snug font-medium text-white/95 {size === 'sm' ? 'text-[13px]' : 'text-sm'}">
      {video.title}
    </h3>
    <p class="mt-1 truncate text-xs text-white/40">
      {#if video.category}<span class="text-white/55">{video.category.name}</span>{/if}
      {#if video.category && (video.year || video.channel)}<span class="mx-1.5 text-white/20">·</span>{/if}
      {video.year || video.channel || ''}
    </p>
  </div>
</a>
