<script>
  import Icon from './Icon.svelte'

  let { open = $bindable(false), title = '', width = 'max-w-lg', children, footer, onclose } = $props()

  let dialog = $state()

  $effect(() => {
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  })

  function close() {
    open = false
    onclose?.()
  }
</script>

<dialog
  bind:this={dialog}
  class="m-auto w-[calc(100%-2rem)] {width} rounded-3xl border border-white/10 bg-coal p-0 text-white shadow-2xl shadow-black backdrop:bg-black/75 backdrop:backdrop-blur-sm"
  onclose={() => open && close()}
  onclick={(e) => e.target === dialog && close()}
>
  {#if open}
    <div class="rise flex max-h-[85dvh] flex-col">
      <header class="flex items-center justify-between gap-4 px-6 pt-5 pb-3">
        <h2 class="text-base font-semibold tracking-tight">{title}</h2>
        <button class="btn-icon -mr-2" onclick={close} aria-label="Close"><Icon name="x" /></button>
      </header>
      <div class="overflow-y-auto px-6 pb-6">
        {@render children?.()}
      </div>
      {#if footer}
        <footer class="flex justify-end gap-2 border-t border-white/[0.07] px-6 py-4">
          {@render footer()}
        </footer>
      {/if}
    </div>
  {/if}
</dialog>
