<script>
  let { value = 0, indeterminate = false, class: klass = '', thin = false } = $props()
</script>

<div
  class="relative overflow-hidden rounded-full bg-white/[0.08] {thin ? 'h-[2px]' : 'h-1'} {klass}"
  role="progressbar"
  aria-valuemin="0"
  aria-valuemax="100"
  aria-valuenow={indeterminate ? undefined : Math.round(value)}
>
  {#if indeterminate}
    <div class="indet absolute inset-y-0 w-1/3 rounded-full bg-accent"></div>
  {:else}
    <div
      class="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
      style="width: {Math.max(0, Math.min(100, value))}%"
    ></div>
  {/if}
</div>

<style>
  .indet {
    animation: slide 1.3s cubic-bezier(0.65, 0, 0.35, 1) infinite;
  }
  @keyframes slide {
    from { left: -35%; }
    to { left: 100%; }
  }
</style>
