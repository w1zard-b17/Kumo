<script>
  import Icon from '../components/Icon.svelte'
  import Wordmark from '../components/Wordmark.svelte'
  import { post } from '../lib/api.js'
  import { app } from '../lib/store.svelte.js'

  let password = $state('')
  let error = $state('')
  let busy = $state(false)

  async function submit(e) {
    e.preventDefault()
    busy = true
    error = ''
    try {
      await post('/auth/login', { password })
      app.auth = { required: true, authenticated: true }
    } catch (err) {
      error = err.status === 401 ? 'Wrong password.' : err.message
      password = ''
    } finally {
      busy = false
    }
  }
</script>

<div class="grid min-h-dvh place-items-center px-6">
  <form class="rise w-full max-w-xs text-center" onsubmit={submit}>
    <div class="flex justify-center"><Wordmark /></div>
    <p class="mt-10 text-sm text-white/45">This library is private.</p>
    <label class="relative mt-5 block">
      <Icon name="lock" size={16} class="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-white/35" />
      <!-- svelte-ignore a11y_autofocus -->
      <input class="field !rounded-full !py-3 !pl-11" type="password" placeholder="Password" bind:value={password} autocomplete="current-password" autofocus />
    </label>
    {#if error}<p class="mt-3 text-sm text-white/75">{error}</p>{/if}
    <button class="btn-primary mt-5 h-11 w-full" disabled={busy || !password}>Enter</button>
  </form>
</div>
