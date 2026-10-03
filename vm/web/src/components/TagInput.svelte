<script>
  import Icon from './Icon.svelte'

  let { tags = $bindable([]), suggestions = [], placeholder = 'Add a tag…' } = $props()
  let text = $state('')

  const available = $derived(
    suggestions
      .filter((s) => !tags.some((t) => t.toLowerCase() === s.toLowerCase()))
      .filter((s) => !text || s.toLowerCase().includes(text.toLowerCase()))
      .slice(0, 10),
  )

  function add(value) {
    const v = value.trim().replace(/,$/, '').slice(0, 40)
    if (v && !tags.some((t) => t.toLowerCase() === v.toLowerCase())) tags = [...tags, v]
    text = ''
  }

  function remove(t) {
    tags = tags.filter((x) => x !== t)
  }

  function keydown(e) {
    if ((e.key === 'Enter' || e.key === ',') && text.trim()) {
      e.preventDefault()
      add(text)
    } else if (e.key === 'Backspace' && !text && tags.length) {
      tags = tags.slice(0, -1)
    }
  }
</script>

<div
  class="field flex min-h-11 flex-wrap items-center gap-1.5 !py-1.5 focus-within:border-accent/70"
>
  {#each tags as t (t)}
    <span class="inline-flex items-center gap-1 rounded-full bg-white/[0.08] py-0.5 pr-1 pl-2.5 text-xs text-white/90">
      {t}
      <button type="button" class="rounded-full p-0.5 text-white/40 hover:text-white" onclick={() => remove(t)} aria-label="Remove {t}">
        <Icon name="x" size={12} />
      </button>
    </span>
  {/each}
  <input
    class="min-w-24 flex-1 bg-transparent py-1 text-sm outline-none placeholder:text-white/30"
    bind:value={text}
    onkeydown={keydown}
    onblur={() => text.trim() && add(text)}
    {placeholder}
  />
</div>
{#if available.length}
  <div class="mt-2 flex flex-wrap gap-1.5">
    {#each available as s (s)}
      <button type="button" class="chip !py-0.5" onclick={() => add(s)}>
        <Icon name="plus" size={11} />{s}
      </button>
    {/each}
  </div>
{/if}
