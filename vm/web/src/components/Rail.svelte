<script>
  import Icon from './Icon.svelte'

  let { title, href = null, children } = $props()
</script>

<section class="rise">
  <div class="mb-4 flex items-end justify-between gap-4">
    <h2 class="text-[15px] font-semibold tracking-tight text-white">{title}</h2>
    {#if href}
      <a {href} class="inline-flex items-center gap-1 text-xs text-white/45 transition-colors hover:text-accent">
        See all <Icon name="chevron-right" size={14} />
      </a>
    {/if}
  </div>
  {@render children()}
</section>
