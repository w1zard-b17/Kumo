<script>
  import Icon from './Icon.svelte'

  let { value = $bindable(0), readonly = false, size = 18, onchange } = $props()
  let hover = $state(0)
</script>

<div class="inline-flex items-center gap-0.5" role={readonly ? 'img' : 'radiogroup'} aria-label="Rating {value} of 5">
  {#each [1, 2, 3, 4, 5] as n}
    {#if readonly}
      <span class={n <= value ? 'text-accent' : 'text-white/15'}>
        <Icon name={n <= value ? 'star-fill' : 'star'} {size} />
      </span>
    {:else}
      <button
        type="button"
        class="rounded p-0.5 transition-transform hover:scale-110 {n <= (hover || value) ? 'text-accent' : 'text-white/20'}"
        aria-label="{n} star{n > 1 ? 's' : ''}"
        onmouseenter={() => (hover = n)}
        onmouseleave={() => (hover = 0)}
        onclick={() => {
          value = value === n ? 0 : n
          onchange?.(value)
        }}
      >
        <Icon name={n <= (hover || value) ? 'star-fill' : 'star'} {size} />
      </button>
    {/if}
  {/each}
</div>
