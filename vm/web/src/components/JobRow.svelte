<script>
  import Icon from './Icon.svelte'
  import ProgressBar from './ProgressBar.svelte'
  import { post, del } from '../lib/api.js'
  import { refreshJobs, fail, toast } from '../lib/store.svelte.js'
  import { bytes, speed, eta, ago } from '../lib/format.js'

  let { job, compact = false, onchange } = $props()
  let busy = $state(false)

  const running = $derived(['downloading', 'converting', 'uploading'].includes(job.status))
  const LABEL = {
    queued: 'Queued',
    downloading: 'Downloading',
    converting: 'Converting to MP4',
    uploading: 'Moving to storage',
    paused: 'Paused',
    done: 'Done',
    failed: 'Failed',
    canceled: 'Canceled',
  }

  const detail = $derived.by(() => {
    if (job.status === 'downloading') {
      const parts = [`${Math.round(job.progress)}%`]
      if (job.total_bytes) parts.push(`${bytes(job.downloaded_bytes)} of ${bytes(job.total_bytes)}`)
      if (job.speed) parts.push(speed(job.speed))
      if (job.eta) parts.push(eta(job.eta))
      return parts.join('  ·  ')
    }
    if (job.status === 'uploading') return `${Math.round(job.progress)}%${job.total_bytes ? `  ·  ${bytes(job.total_bytes)}` : ''}`
    if (job.status === 'queued' && job.next_attempt_at) {
      const s = Math.max(0, Math.round(job.next_attempt_at - Date.now() / 1000))
      return `Retrying in ${s < 60 ? `${s}s` : `${Math.round(s / 60)}m`} · attempt ${job.attempts + 1}`
    }
    if (job.status === 'queued') return `${job.options?.quality === 'best' ? 'Best' : `${job.options?.quality}p`} · waiting for the worker`
    if (['done', 'failed', 'canceled'].includes(job.status)) return ago(job.finished_at)
    return ''
  })

  async function act(action) {
    busy = true
    try {
      if (action === 'forget') await del(`/jobs/${job.id}`)
      else await post(`/jobs/${job.id}/${action}`)
      if (action === 'cancel') toast('Download canceled')
      await refreshJobs()
      onchange?.()
    } catch (e) {
      fail(e)
    } finally {
      busy = false
    }
  }
</script>

<div class="group flex items-center gap-4 {compact ? 'py-2.5' : 'py-4'}">
  <a
    href={job.video_id && job.status === 'done' ? `/v/${job.video_id}` : null}
    class="relative aspect-video shrink-0 overflow-hidden rounded-lg bg-char ring-1 ring-white/[0.06] {compact ? 'w-20' : 'w-28 sm:w-36'}"
  >
    {#if job.poster}
      <img src={job.poster} alt="" loading="lazy" class="size-full object-cover {job.status === 'done' ? '' : 'opacity-70'}" />
    {/if}
    {#if running}
      <span class="absolute top-1.5 left-1.5 size-1.5 rounded-full bg-accent pulse-dot"></span>
    {/if}
  </a>

  <div class="min-w-0 flex-1">
    <p class="truncate text-sm font-medium text-white/95">{job.title || job.url}</p>
    <p class="mt-1 flex items-center gap-2 truncate text-xs">
      <span
        class="{job.status === 'failed' ? 'text-white' : running || job.status === 'done' ? 'text-accent' : 'text-white/55'}"
        >{LABEL[job.status]}</span
      >
      {#if detail}<span class="tabular truncate text-white/35">{detail}</span>{/if}
    </p>
    {#if job.error && job.status !== 'done'}
      <p class="mt-1.5 flex items-start gap-1.5 text-xs text-white/60">
        <Icon name="alert" size={13} class="mt-px shrink-0" />{job.error}
      </p>
    {/if}
    {#if running || job.status === 'paused' || (job.status === 'queued' && job.progress > 0)}
      <ProgressBar
        class="mt-2.5"
        value={job.progress}
        indeterminate={job.status === 'converting' || (job.status === 'downloading' && !job.progress)}
        thin={compact}
      />
    {/if}
  </div>

  <div class="flex shrink-0 items-center gap-0.5 {compact ? '' : 'opacity-80 transition-opacity group-hover:opacity-100'}">
    {#if job.status === 'downloading' || job.status === 'converting' || job.status === 'queued'}
      <button class="btn-icon" disabled={busy} onclick={() => act('pause')} aria-label="Pause" title="Pause"><Icon name="pause" size={15} /></button>
    {/if}
    {#if job.status === 'paused'}
      <button class="btn-icon text-accent" disabled={busy} onclick={() => act('resume')} aria-label="Resume" title="Resume"><Icon name="play" size={15} /></button>
    {/if}
    {#if job.status === 'failed' || (job.status === 'queued' && job.next_attempt_at)}
      <button class="btn-icon" disabled={busy} onclick={() => act('retry')} aria-label="Retry now" title="Retry now"><Icon name="refresh" size={16} /></button>
    {/if}
    {#if ['queued', 'downloading', 'converting', 'uploading', 'paused', 'failed'].includes(job.status)}
      <button class="btn-icon" disabled={busy} onclick={() => act('cancel')} aria-label={job.status === 'failed' ? 'Discard' : 'Cancel'} title={job.status === 'failed' ? 'Discard' : 'Cancel'}><Icon name="x" size={16} /></button>
    {/if}
    {#if !compact && ['done', 'canceled'].includes(job.status)}
      <button class="btn-icon" disabled={busy} onclick={() => act('forget')} aria-label="Remove from history" title="Remove from history"><Icon name="trash" size={15} /></button>
    {/if}
  </div>
</div>
