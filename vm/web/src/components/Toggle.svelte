<script>
  let { checked = $bindable(false), label = '', hint = '', disabled = false, onchange } = $props()
</script>

<label class="flex cursor-pointer items-center justify-between gap-6 py-1 {disabled ? 'pointer-events-none opacity-40' : ''}">
  <span class="min-w-0">
    <span class="block text-sm text-white/90">{label}</span>
    {#if hint}<span class="mt-0.5 block text-xs text-white/40">{hint}</span>{/if}
  </span>
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    {disabled}
    class="relative h-6 w-10 shrink-0 rounded-full border transition-colors duration-200
           {checked ? 'border-accent bg-accent' : 'border-white/15 bg-white/[0.06]'}"
    onclick={() => {
      checked = !checked
      onchange?.(checked)
    }}
  >
    <span
      class="absolute top-1/2 size-4 -translate-y-1/2 rounded-full transition-all duration-200 ease-out
             {checked ? 'left-[20px] bg-ink' : 'left-[3px] bg-white/70'}"
    ></span>
  </button>
</label>
