<script>
  import { onMount } from 'svelte'
  import Icon from './components/Icon.svelte'
  import Wordmark from './components/Wordmark.svelte'
  import Toasts from './components/Toasts.svelte'
  import { route, match } from './lib/router.svelte.js'
  import { app, loadAuth, loadCategories, loadSettings, loadStorage, refreshJobs } from './lib/store.svelte.js'
  import { bytes, pct } from './lib/format.js'

  import Home from './pages/Home.svelte'
  import Add from './pages/Add.svelte'
  import Downloads from './pages/Downloads.svelte'
  import Library from './pages/Library.svelte'
  import Detail from './pages/Detail.svelte'
  import Player from './pages/Player.svelte'
  import Collections from './pages/Collections.svelte'
  import Collection from './pages/Collection.svelte'
  import Settings from './pages/Settings.svelte'
  import Login from './pages/Login.svelte'

  const ROUTES = [
    ['/', Home],
    ['/add', Add],
    ['/downloads', Downloads],
    ['/library', Library],
    ['/v/:id', Detail],
    ['/watch/:id', Player],
    ['/collections', Collections],
    ['/collections/:id', Collection],
    ['/settings', Settings],
  ]

  const NAV = [
    { href: '/', icon: 'home', label: 'Home' },
    { href: '/library', icon: 'library', label: 'Library' },
    { href: '/downloads', icon: 'download', label: 'Downloads' },
    { href: '/collections', icon: 'layers', label: 'Collections' },
    { href: '/settings', icon: 'settings', label: 'Settings' },
  ]

  let ready = $state(false)
  let error = $state('')

  const current = $derived.by(() => {
    for (const [pattern, component] of ROUTES) {
      const params = match(pattern, route.path)
      if (params) return { component, params, pattern }
    }
    return { component: Home, params: {}, pattern: '/' }
  })
  const immersive = $derived(current.pattern === '/watch/:id')
  const running = $derived(app.active.filter((j) => ['downloading', 'converting', 'uploading'].includes(j.status)).length)

  function isActive(href) {
    if (href === '/') return route.path === '/' || route.path === '/add'
    return route.path === href || route.path.startsWith(href + '/') || (href === '/library' && route.path.startsWith('/v/'))
  }

  async function boot() {
    error = ''
    try {
      const a = await loadAuth()
      if (a.required && !a.authenticated) {
        ready = true
        return
      }
      await Promise.all([loadCategories(), loadSettings()])
      loadStorage()
      refreshJobs()
      ready = true
    } catch (e) {
      error = e.message
    }
  }

  onMount(boot)

  $effect(() => {
    // re-boot after logging in
    if (ready && app.auth?.authenticated && !app.settings) boot()
  })
</script>

{#if error}
  <div class="grid min-h-dvh place-items-center p-6">
    <div class="text-center">
      <Wordmark />
      <p class="mt-6 text-sm text-white/60">{error}</p>
      <button class="btn-ghost mt-5" onclick={boot}><Icon name="refresh" size={15} /> Try again</button>
    </div>
  </div>
{:else if !ready}
  <div class="grid min-h-dvh place-items-center"><span class="size-1.5 rounded-full bg-accent pulse-dot"></span></div>
{:else if app.auth?.required && !app.auth?.authenticated}
  <Login />
{:else if immersive}
  {#key current.params.id}
    <current.component params={current.params} />
  {/key}
{:else}
  <div class="min-h-dvh md:pl-60">
    <!-- sidebar -->
    <aside class="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-white/[0.06] bg-ink px-4 py-6 md:flex">
      <div class="px-2"><Wordmark /></div>

      <nav class="mt-10 flex flex-col gap-0.5" aria-label="Main">
        {#each NAV as item (item.href)}
          {@const on = isActive(item.href)}
          <a
            href={item.href}
            class="group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors
                   {on ? 'text-white' : 'text-white/45 hover:bg-white/[0.03] hover:text-white/85'}"
            aria-current={on ? 'page' : undefined}
          >
            <span
              class="absolute top-1/2 left-0 h-4 w-[2px] -translate-y-1/2 rounded-full bg-accent transition-opacity {on ? 'opacity-100' : 'opacity-0'}"
            ></span>
            <Icon name={item.icon} size={18} class={on ? 'text-accent' : ''} />
            {item.label}
            {#if item.href === '/downloads' && app.active.length}
              <span class="tabular ml-auto rounded-full px-1.5 text-[11px] font-medium {running ? 'bg-accent text-ink' : 'bg-white/10 text-white/70'}">
                {app.active.length}
              </span>
            {/if}
            {#if item.href === '/library' && app.unsorted}
              <span class="tabular ml-auto rounded-full bg-white/10 px-1.5 text-[11px] font-medium text-white/70" title="Unsorted">
                {app.unsorted}
              </span>
            {/if}
          </a>
        {/each}
      </nav>

      <a href="/add" class="btn-primary mt-6 w-full !rounded-xl"><Icon name="plus" size={16} stroke={2} /> Add a link</a>

      <div class="mt-auto px-2">
        {#if app.storage?.reachable && app.storage.online}
          {@const s = app.storage}
          {@const total = s.quota || s.disk_total}
          {@const used = s.quota ? s.used : s.disk_total - s.disk_free}
          <a href="/settings#storage" class="block rounded-xl p-2 -m-2 transition-colors hover:bg-white/[0.03]">
            <p class="label flex items-center gap-1.5"><Icon name="hdd" size={12} /> {s.disk}</p>
            <div class="mt-2.5 h-[3px] overflow-hidden rounded-full bg-white/[0.08]">
              <div class="h-full rounded-full bg-accent" style="width:{pct(used, total)}%"></div>
            </div>
            <p class="tabular mt-2 text-xs text-white/45">{bytes(s.available)} free</p>
          </a>
        {:else if app.storage}
          <a href="/settings#storage" class="flex items-center gap-2 text-xs text-white/55 hover:text-white">
            <span class="size-1.5 rounded-full border border-white/60"></span> Storage offline
          </a>
        {/if}
      </div>
    </aside>

    <!-- mobile top bar -->
    <header class="sticky top-0 z-30 flex items-center justify-between border-b border-white/[0.06] bg-ink/85 px-4 py-3 backdrop-blur-xl md:hidden">
      <Wordmark />
      <a href="/add" class="btn-icon text-accent" aria-label="Add a link"><Icon name="plus" size={20} /></a>
    </header>

    <main class="mx-auto max-w-[1440px] px-4 pt-6 pb-28 sm:px-6 md:px-10 md:pt-10 md:pb-16">
      {#key current.pattern + (current.params.id || '')}
        <current.component params={current.params} />
      {/key}
    </main>

    <!-- mobile tab bar -->
    <nav
      class="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-white/[0.06] bg-ink/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
      aria-label="Main"
    >
      {#each NAV as item (item.href)}
        {@const on = isActive(item.href)}
        <a href={item.href} class="relative flex flex-col items-center gap-1 py-2.5 text-[10px] {on ? 'text-white' : 'text-white/40'}">
          <Icon name={item.icon} size={20} class={on ? 'text-accent' : ''} />
          {item.label}
          {#if item.href === '/downloads' && running}
            <span class="absolute top-2 right-[calc(50%-16px)] size-1.5 rounded-full bg-accent pulse-dot"></span>
          {/if}
        </a>
      {/each}
    </nav>
  </div>
{/if}

<Toasts />
