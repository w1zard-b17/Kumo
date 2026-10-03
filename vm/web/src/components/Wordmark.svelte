<script>
  let { compact = false } = $props()
</script>

<a href="/" class="group inline-flex items-center gap-2.5" aria-label="Kumo Film home">
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M7.2 18.5h10.3a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.8 9.1a4.75 4.75 0 0 0 .4 9.4Z"
      stroke="var(--color-accent)"
      stroke-width="1.7"
      stroke-linejoin="round"
    />
  </svg>
  {#if !compact}
    <span class="text-[17px] font-semibold tracking-[-0.02em] text-white">
      kumo<span class="ml-1 text-[10px] font-medium uppercase tracking-[0.3em] text-white/40 transition-colors group-hover:text-accent">film</span>
    </span>
  {/if}
</a>
