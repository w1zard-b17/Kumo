<script>
  import Icon from './Icon.svelte'

  let { icon = 'cloud', title, text = '', children } = $props()
</script>

<div class="rise flex flex-col items-center px-6 py-20 text-center">
  <div class="grid size-14 place-items-center rounded-2xl border border-white/[0.08] text-accent">
    <Icon name={icon} size={24} stroke={1.4} />
  </div>
  <h3 class="mt-5 text-base font-medium text-white">{title}</h3>
  {#if text}<p class="mt-1.5 max-w-sm text-sm leading-relaxed text-white/45">{text}</p>{/if}
  {#if children}<div class="mt-6">{@render children()}</div>{/if}
</div>
