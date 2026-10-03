<script>
  import Icon from './Icon.svelte'
  import { post } from '../lib/api.js'

  let { onresult, autofocus = false, large = true } = $props()

  let url = $state('')
  let loading = $state(false)
  let error = $state('')
  let input = $state()

  const YT = /(youtube\.com|youtu\.be|youtube-nocookie\.com)|^[A-Za-z0-9_-]{11}$/i

  $effect(() => {
    if (autofocus) input?.focus()
  })

  export async function fetchUrl(value = url, playlist = false) {
    url = value
    error = ''
    if (!url.trim()) return
    if (!YT.test(url.trim())) {
      error = "That doesn't look like a YouTube link."
      return
    }
    loading = true
    try {
      onresult?.(await post('/fetch', { url: url.trim(), playlist }))
    } catch (e) {
      error = e.message
      onresult?.(null)
    } finally {
      loading = false
    }
  }

  async function paste(e) {
    const text = e.clipboardData?.getData('text')?.trim()
    if (text && YT.test(text)) {
      e.preventDefault()
      await fetchUrl(text)
    }
  }
</script>

<form
  class="group relative flex items-center rounded-full border bg-coal transition-all duration-300
         {error ? 'border-white/40' : 'border-white/10 hover:border-white/20 focus-within:border-accent/70 focus-within:shadow-[0_0_0_4px_rgba(43,224,128,0.08)]'}
         {large ? 'h-16 pl-6 pr-2' : 'h-12 pl-4 pr-1.5'}"
  onsubmit={(e) => {
    e.preventDefault()
    fetchUrl()
  }}
>
  <span class="shrink-0 text-white/35 transition-colors group-focus-within:text-accent">
    <Icon name="link" size={large ? 20 : 17} />
  </span>
  <input
    bind:this={input}
    bind:value={url}
    onpaste={paste}
    type="text"
    inputmode="url"
    autocomplete="off"
    spellcheck="false"
    class="h-full min-w-0 flex-1 bg-transparent px-4 outline-none placeholder:text-white/30 {large ? 'text-base' : 'text-sm'}"
    placeholder="Paste a YouTube link"
    aria-label="YouTube link"
  />
  <button type="submit" class="btn-primary shrink-0 {large ? 'h-12 px-6' : 'h-9 px-4'}" disabled={loading || !url.trim()}>
    {#if loading}
      <span class="size-4 animate-spin rounded-full border-2 border-ink/30 border-t-ink"></span> Fetching
    {:else}
      Fetch <Icon name="arrow-right" size={16} stroke={2} />
    {/if}
  </button>
</form>
{#if error}
  <p class="rise mt-3 flex items-center justify-center gap-2 text-sm text-white/75">
    <Icon name="alert" size={15} />{error}
  </p>
{/if}
