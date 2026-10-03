<script>
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import { get, put } from '../lib/api.js'
  import { app, toast, fail } from '../lib/store.svelte.js'
  import { navigate, route } from '../lib/router.svelte.js'
  import { clock, pct } from '../lib/format.js'

  let { params } = $props()

  const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]
  const store = {
    get: (k, d) => {
      try {
        const v = localStorage.getItem(`kumo.${k}`)
        return v === null ? d : JSON.parse(v)
      } catch {
        return d
      }
    },
    set: (k, v) => {
      try {
        localStorage.setItem(`kumo.${k}`, JSON.stringify(v))
      } catch {}
    },
  }

  let v = $state(null)
  let next = $state(null)
  let el = $state()
  let shell = $state()
  let bar = $state()

  let paused = $state(true)
  let time = $state(0)
  let dur = $state(0)
  let buffered = $state(0)
  let volume = $state(store.get('volume', 1))
  let muted = $state(false)
  let rate = $state(1)
  let waiting = $state(false)
  let ended = $state(false)
  let fullscreen = $state(false)
  let track = $state(-1)
  let menu = $state(null) // 'cc' | 'speed' | null
  let controls = $state(true)
  let hover = $state(null) // { x, t } over the seek bar
  let scrubbing = $state(false)
  let countdown = $state(0)
  let error = $state('')

  let hideTimer, countdownTimer
  let lastSaved = 0

  const chapter = $derived(v?.chapters?.length ? [...v.chapters].reverse().find((c) => time >= c.start) : null)
  const hoverChapter = $derived(hover && v?.chapters?.length ? [...v.chapters].reverse().find((c) => hover.t >= c.start) : null)

  onMount(() => {
    load()
    const onFs = () => (fullscreen = !!document.fullscreenElement)
    const onHide = () => document.visibilityState === 'hidden' && beacon()
    document.addEventListener('fullscreenchange', onFs)
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('pagehide', beacon)
    return () => {
      beacon()
      document.removeEventListener('fullscreenchange', onFs)
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('pagehide', beacon)
      clearTimeout(hideTimer)
      clearInterval(countdownTimer)
    }
  })

  async function load() {
    try {
      v = await get(`/videos/${params.id}`)
      if (v.status !== 'ready') {
        error = 'This title is still downloading.'
        return
      }
      get(`/videos/${params.id}/next`).then((r) => (next = r.video)).catch(() => {})
    } catch (e) {
      error = e.message
    }
  }

  function onMeta() {
    dur = el.duration
    el.volume = volume
    el.playbackRate = rate
    const t = route.query.get('t')
    if (t !== null) el.currentTime = Math.min(Number(t) || 0, dur - 1)
    else if (!v.playback.watched && v.playback.position > 30 && v.playback.position < dur * 0.95) {
      el.currentTime = v.playback.position
      toast(`Resumed at ${clock(v.playback.position)}`, {
        action: { label: 'Start over', run: () => (el.currentTime = 0) },
      })
    }
    time = el.currentTime
    const preferred = store.get('subs', null)
    if (preferred && v.subtitles?.length) {
      const i = v.subtitles.findIndex((s) => s.lang === preferred)
      if (i >= 0) setTrack(i, false)
    }
    el.play().catch(() => (paused = true))
  }

  function body() {
    return { position: el?.currentTime || 0, duration: el?.duration || 0 }
  }

  async function save() {
    if (!el || !el.duration) return
    lastSaved = el.currentTime
    try {
      const p = await put(`/videos/${params.id}/playback`, body())
      if (v) v.playback.watched = p.watched
    } catch {}
  }

  function beacon() {
    if (!el || !el.duration || Math.abs(el.currentTime - lastSaved) < 1) return
    lastSaved = el.currentTime
    const blob = new Blob([JSON.stringify(body())], { type: 'application/json' })
    navigator.sendBeacon?.(`/api/videos/${params.id}/playback`, blob)
  }

  function onTime() {
    time = el.currentTime
    if (el.buffered.length) buffered = el.buffered.end(el.buffered.length - 1)
    if (!el.paused && Math.abs(time - lastSaved) >= 5) save()
  }

  function onEnded() {
    ended = true
    save()
    showControls()
    if (next && (app.settings?.autoplay_next ?? true)) {
      countdown = 8
      countdownTimer = setInterval(() => {
        countdown--
        if (countdown <= 0) {
          clearInterval(countdownTimer)
          playNext()
        }
      }, 1000)
    }
  }

  function playNext() {
    clearInterval(countdownTimer)
    if (next) navigate(`/watch/${next.id}`, { replace: true })
  }

  function cancelNext() {
    clearInterval(countdownTimer)
    countdown = 0
  }

  function toggle() {
    if (!el) return
    if (el.paused) {
      ended = false
      cancelNext()
      el.play()
    } else el.pause()
  }

  function seek(to) {
    if (!el || !dur) return
    el.currentTime = Math.max(0, Math.min(dur - 0.1, to))
    time = el.currentTime
    ended = false
    showControls()
  }

  function setVolume(x) {
    volume = Math.max(0, Math.min(1, x))
    muted = volume === 0
    if (el) {
      el.volume = volume
      el.muted = muted
    }
    store.set('volume', volume)
  }

  function toggleMute() {
    muted = !muted
    el.muted = muted
    if (!muted && volume === 0) setVolume(0.6)
  }

  function setRate(r) {
    rate = r
    el.playbackRate = r
    menu = null
  }

  function setTrack(i, remember = true) {
    track = i
    const tracks = el?.textTracks || []
    for (let n = 0; n < tracks.length; n++) tracks[n].mode = n === i ? 'showing' : 'hidden'
    if (remember) store.set('subs', i >= 0 ? v.subtitles[i].lang : null)
    menu = null
  }

  // keep subtitles clear of the control bar while it is visible
  function placeCues() {
    const t = track >= 0 ? el?.textTracks?.[track] : null
    for (const cue of t?.cues || []) cue.line = controls ? -5 : 'auto'
  }

  $effect(() => {
    controls, track
    placeCues()
  })

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await shell.requestFullscreen()
    } catch {}
  }

  function showControls() {
    controls = true
    clearTimeout(hideTimer)
    hideTimer = setTimeout(() => {
      if (!paused && !menu && !scrubbing) controls = false
    }, 2600)
  }

  function exit() {
    save()
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    navigate(`/v/${params.id}`, { replace: true })
  }

  function ratioAt(e) {
    const r = bar.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
  }

  function barMove(e) {
    const x = ratioAt(e)
    hover = { x: x * 100, t: x * dur }
    if (scrubbing) time = x * dur
  }

  function barDown(e) {
    scrubbing = true
    bar.setPointerCapture(e.pointerId)
    barMove(e)
  }

  function barUp(e) {
    if (!scrubbing) return
    scrubbing = false
    seek(ratioAt(e) * dur)
  }

  function key(e) {
    if (e.target.closest?.('input, textarea, select') || e.metaKey || e.ctrlKey || e.altKey) return
    const k = e.key
    const handled = {
      ' ': toggle,
      k: toggle,
      K: toggle,
      ArrowLeft: () => seek(time - 5),
      ArrowRight: () => seek(time + 5),
      j: () => seek(time - 10),
      l: () => seek(time + 10),
      ArrowUp: () => setVolume(volume + 0.1),
      ArrowDown: () => setVolume(volume - 0.1),
      m: toggleMute,
      f: toggleFullscreen,
      c: () => v?.subtitles?.length && setTrack(track >= 0 ? -1 : 0),
      '>': () => setRate(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(rate) + 1)]),
      '<': () => setRate(SPEEDS[Math.max(0, SPEEDS.indexOf(rate) - 1)]),
      Escape: () => (menu ? (menu = null) : !document.fullscreenElement && exit()),
      N: playNext,
    }[k]
    if (handled) {
      e.preventDefault()
      handled()
      showControls()
    } else if (/^[0-9]$/.test(k) && dur) {
      seek((Number(k) / 10) * dur)
    }
  }
</script>

<svelte:window onkeydown={key} />

<div
  bind:this={shell}
  class="relative h-dvh w-full overflow-hidden bg-black select-none {controls ? '' : 'cursor-none'}"
  onpointermove={showControls}
  role="application"
  aria-label="Video player"
>
  {#if error}
    <div class="grid h-full place-items-center p-6 text-center">
      <div>
        <p class="text-white/70">{error}</p>
        <button class="btn-ghost mt-6" onclick={exit}><Icon name="arrow-left" size={16} /> Back</button>
      </div>
    </div>
  {:else if v}
    <!-- svelte-ignore a11y_media_has_caption -->
    <video
      bind:this={el}
      src="/api/videos/{v.id}/stream"
      poster={v.poster}
      class="absolute inset-0 size-full object-contain"
      preload="metadata"
      playsinline
      onloadedmetadata={onMeta}
      ontimeupdate={onTime}
      onprogress={() => el.buffered.length && (buffered = el.buffered.end(el.buffered.length - 1))}
      onplay={() => {
        paused = false
        ended = false
        showControls()
      }}
      onpause={() => {
        paused = true
        controls = true
        save()
      }}
      onwaiting={() => (waiting = true)}
      onplaying={() => (waiting = false)}
      oncanplay={() => (waiting = false)}
      onended={onEnded}
      onerror={() => (error = 'The video could not be loaded. Is the storage host reachable?')}
      onclick={toggle}
      ondblclick={toggleFullscreen}
    >
      {#each v.subtitles || [] as s}
        <track kind="subtitles" src={s.src} srclang={s.lang} label={s.label} onload={placeCues} />
      {/each}
    </video>

    {#if v.resolution === 'audio'}
      <img src={v.poster} alt="" class="pointer-events-none absolute inset-0 m-auto max-h-[60%] max-w-[80%] rounded-2xl object-contain shadow-2xl" />
    {/if}

    {#if waiting && !paused}
      <div class="pointer-events-none absolute inset-0 grid place-items-center">
        <span class="size-12 animate-spin rounded-full border-2 border-white/15 border-t-accent"></span>
      </div>
    {/if}

    {#if paused && !ended && !waiting}
      <button class="absolute inset-0 m-auto grid size-20 place-items-center rounded-full bg-accent/95 text-ink shadow-2xl transition-transform hover:scale-105" onclick={toggle} aria-label="Play">
        <Icon name="play" size={30} />
      </button>
    {/if}

    <!-- top -->
    <div class="pointer-events-none absolute inset-x-0 top-0 bg-gradient-to-b from-black/80 to-transparent px-4 pt-4 pb-16 transition-opacity duration-300 md:px-8 md:pt-6 {controls ? 'opacity-100' : 'opacity-0'}">
      <div class="pointer-events-auto flex items-center gap-3">
        <button class="btn-icon size-10" onclick={exit} aria-label="Back"><Icon name="arrow-left" size={20} /></button>
        <div class="min-w-0">
          <p class="truncate text-[15px] font-medium">{v.title}</p>
          <p class="truncate text-xs text-white/50">{v.category?.name || 'Unsorted'}{v.subcategory ? ` · ${v.subcategory}` : ''}</p>
        </div>
      </div>
    </div>

    <!-- next up -->
    {#if ended && next}
      <div class="rise absolute right-4 bottom-32 w-80 max-w-[calc(100%-2rem)] overflow-hidden rounded-2xl border border-white/10 bg-coal/95 shadow-2xl backdrop-blur md:right-8">
        <div class="relative aspect-video">
          <img src={next.poster} alt="" class="size-full object-cover" />
          {#if countdown > 0}
            <div class="absolute inset-x-0 bottom-0 h-1 bg-white/10"><div class="h-full bg-accent transition-[width] duration-1000 ease-linear" style="width:{((8 - countdown) / 8) * 100}%"></div></div>
          {/if}
        </div>
        <div class="p-4">
          <p class="label">{countdown > 0 ? `Up next in ${countdown}` : 'Up next'}</p>
          <p class="mt-1.5 line-clamp-2 text-sm font-medium">{next.title}</p>
          <div class="mt-4 flex gap-2">
            <button class="btn-primary flex-1 !py-1.5" onclick={playNext}><Icon name="play" size={14} /> Play</button>
            {#if countdown > 0}<button class="btn-ghost !py-1.5" onclick={cancelNext}>Cancel</button>{/if}
          </div>
        </div>
      </div>
    {/if}

    <!-- bottom controls -->
    <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent px-4 pt-20 pb-4 transition-opacity duration-300 md:px-8 md:pb-6 {controls ? 'opacity-100' : 'pointer-events-none opacity-0'}">
      <!-- seek bar -->
      <div
        bind:this={bar}
        class="group relative flex h-5 cursor-pointer items-center touch-none"
        onpointermove={barMove}
        onpointerdown={barDown}
        onpointerup={barUp}
        onpointerleave={() => !scrubbing && (hover = null)}
        role="slider"
        tabindex="-1"
        aria-label="Seek"
        aria-valuemin="0"
        aria-valuemax={Math.round(dur)}
        aria-valuenow={Math.round(time)}
      >
        <div class="relative h-[3px] w-full rounded-full bg-white/20 transition-[height] duration-150 group-hover:h-[5px]">
          <div class="absolute inset-y-0 left-0 rounded-full bg-white/30" style="width:{pct(buffered, dur)}%"></div>
          <div class="absolute inset-y-0 left-0 rounded-full bg-accent" style="width:{pct(time, dur)}%"></div>
          {#each v.chapters || [] as ch}
            {#if ch.start > 0 && dur}
              <span class="absolute inset-y-0 w-[3px] -translate-x-1/2 bg-black" style="left:{pct(ch.start, dur)}%"></span>
            {/if}
          {/each}
          {#if hover}
            <div class="absolute inset-y-0 left-0 rounded-full bg-white/25" style="width:{hover.x}%"></div>
          {/if}
        </div>
        <span
          class="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent shadow-lg transition-transform duration-150 {scrubbing ? 'scale-125' : 'scale-0 group-hover:scale-100'}"
          style="left:{pct(time, dur)}%"
        ></span>
        {#if hover}
          <div
            class="pointer-events-none absolute bottom-6 -translate-x-1/2 rounded-lg bg-black/90 px-2.5 py-1.5 text-center whitespace-nowrap shadow-lg"
            style="left:clamp(40px, {hover.x}%, calc(100% - 40px))"
          >
            {#if hoverChapter}<p class="max-w-56 truncate text-[11px] text-white/70">{hoverChapter.title}</p>{/if}
            <p class="tabular text-xs font-medium">{clock(hover.t)}</p>
          </div>
        {/if}
      </div>

      <div class="mt-2 flex items-center gap-1 md:gap-2">
        <button class="btn-icon size-10 text-white" onclick={toggle} aria-label={paused ? 'Play' : 'Pause'}>
          <Icon name={paused ? 'play' : 'pause'} size={20} />
        </button>
        <button class="btn-icon size-10 text-white/80" onclick={() => seek(time - 10)} aria-label="Back 10 seconds"><Icon name="back-10" size={21} /></button>
        <button class="btn-icon size-10 text-white/80" onclick={() => seek(time + 10)} aria-label="Forward 10 seconds"><Icon name="fwd-10" size={21} /></button>

        <div class="group/vol hidden items-center sm:flex">
          <button class="btn-icon size-10 text-white/80" onclick={toggleMute} aria-label={muted ? 'Unmute' : 'Mute'}>
            <Icon name={muted || volume === 0 ? 'volume-x' : volume < 0.5 ? 'volume-low' : 'volume'} size={20} />
          </button>
          <input
            type="range"
            min="0"
            max="1"
            step="0.02"
            value={muted ? 0 : volume}
            oninput={(e) => setVolume(+e.target.value)}
            class="vol w-0 opacity-0 transition-all duration-200 group-hover/vol:w-24 group-hover/vol:opacity-100 focus:w-24 focus:opacity-100"
            style="--v:{(muted ? 0 : volume) * 100}%"
            aria-label="Volume"
          />
        </div>

        <span class="tabular ml-2 text-xs text-white/75 md:text-[13px]">{clock(time)} <span class="text-white/35">/ {clock(dur)}</span></span>
        {#if chapter}
          <span class="ml-3 hidden truncate text-xs text-white/50 lg:inline">· {chapter.title}</span>
        {/if}

        <div class="ml-auto flex items-center gap-1">
          {#if next}
            <button class="btn-icon size-10 text-white/80" onclick={playNext} aria-label="Next" title="Next: {next.title}"><Icon name="skip-forward" size={18} /></button>
          {/if}

          {#if v.subtitles?.length}
            <div class="relative">
              <button class="btn-icon size-10 {track >= 0 ? 'text-accent' : 'text-white/80'}" onclick={() => (menu = menu === 'cc' ? null : 'cc')} aria-label="Subtitles">
                <Icon name="cc" size={20} />
              </button>
              {#if menu === 'cc'}
                <div class="rise absolute right-0 bottom-12 w-44 rounded-xl border border-white/10 bg-coal/95 p-1.5 shadow-2xl backdrop-blur">
                  <p class="label px-2.5 pt-1.5 pb-2">Subtitles</p>
                  {#each [{ label: 'Off' }, ...v.subtitles] as s, i}
                    <button class="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm hover:bg-white/5" onclick={() => setTrack(i - 1)}>
                      {s.label}
                      {#if track === i - 1}<Icon name="check" size={15} class="text-accent" />{/if}
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}

          <div class="relative">
            <button class="btn-icon tabular h-10 w-auto px-2.5 text-xs font-medium {rate !== 1 ? 'text-accent' : 'text-white/80'}" onclick={() => (menu = menu === 'speed' ? null : 'speed')} aria-label="Playback speed">
              {rate}×
            </button>
            {#if menu === 'speed'}
              <div class="rise absolute right-0 bottom-12 w-32 rounded-xl border border-white/10 bg-coal/95 p-1.5 shadow-2xl backdrop-blur">
                <p class="label px-2.5 pt-1.5 pb-2">Speed</p>
                {#each SPEEDS as r}
                  <button class="tabular flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-white/5" onclick={() => setRate(r)}>
                    {r === 1 ? 'Normal' : `${r}×`}
                    {#if rate === r}<Icon name="check" size={14} class="text-accent" />{/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>

          <button class="btn-icon size-10 text-white/80" onclick={toggleFullscreen} aria-label="Fullscreen">
            <Icon name={fullscreen ? 'minimize' : 'maximize'} size={19} />
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  :global(video::cue) {
    background: rgba(0, 0, 0, 0.62);
    color: #fff;
    font-family: var(--font-sans);
    font-size: clamp(16px, 2.3vw, 30px);
    line-height: 1.35;
  }
  .vol {
    appearance: none;
    height: 3px;
    border-radius: 9999px;
    background: linear-gradient(to right, var(--color-accent) var(--v), rgba(255, 255, 255, 0.2) var(--v));
    cursor: pointer;
  }
  .vol::-webkit-slider-thumb {
    appearance: none;
    width: 12px;
    height: 12px;
    border-radius: 9999px;
    background: #fff;
  }
  .vol::-moz-range-thumb {
    width: 12px;
    height: 12px;
    border: 0;
    border-radius: 9999px;
    background: #fff;
  }
</style>
