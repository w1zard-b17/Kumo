<script>
  import { toasts, dismiss } from '../lib/store.svelte.js'
  import Icon from './Icon.svelte'
</script>

<div class="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6">
  {#each toasts as t (t.id)}
    <div
      class="rise pointer-events-auto flex max-w-md items-center gap-3 rounded-2xl border bg-char/95 py-2.5 pr-2 pl-4 text-sm shadow-xl shadow-black/60 backdrop-blur
             {t.kind === 'error' ? 'border-white/25' : 'border-white/10'}"
      role="status"
    >
      <span class="shrink-0 {t.kind === 'success' ? 'text-accent' : 'text-white/70'}">
        <Icon name={t.kind === 'error' ? 'alert' : t.kind === 'success' ? 'check' : 'cloud'} size={16} />
      </span>
      <span class="text-white/90">{t.message}</span>
      {#if t.action}
        <button
          class="ml-1 rounded-full px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/10"
          onclick={() => {
            t.action.run()
            dismiss(t.id)
          }}>{t.action.label}</button
        >
      {/if}
      <button class="btn-icon size-7" onclick={() => dismiss(t.id)} aria-label="Dismiss"><Icon name="x" size={14} /></button>
    </div>
  {/each}
</div>
