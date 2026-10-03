<script>
  import Icon from './Icon.svelte'
  import TagInput from './TagInput.svelte'
  import { app } from '../lib/store.svelte.js'
  import { TYPE_ICONS, LANGUAGES } from '../lib/format.js'

  let { value = $bindable(), tagSuggestions = [], compact = false, showOptional = true } = $props()
</script>

<div class="space-y-7">
  <section>
    <p class="label mb-3">Type</p>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {#each Object.entries(app.types) as [key, label] (key)}
        <button
          type="button"
          aria-pressed={value.type === key}
          onclick={() => (value.type = key)}
          class="flex items-center gap-2.5 rounded-xl border px-3.5 py-3 text-left text-sm transition-all duration-200
                 {value.type === key
            ? 'border-accent/70 bg-accent/[0.07] text-white'
            : 'border-white/[0.08] text-white/60 hover:border-white/20 hover:text-white'}"
        >
          <span class={value.type === key ? 'text-accent' : 'text-white/40'}><Icon name={TYPE_ICONS[key]} size={17} /></span>
          {label}
        </button>
      {/each}
    </div>
  </section>

  <section>
    <p class="label mb-3">Category <span class="normal-case tracking-normal text-white/25">— required</span></p>
    <div class="grid grid-cols-2 gap-2 {compact ? 'sm:grid-cols-3' : 'sm:grid-cols-3 lg:grid-cols-5'}">
      {#each app.categories as c (c.id)}
        <button
          type="button"
          aria-pressed={value.category_id === c.id}
          onclick={() => (value.category_id = c.id)}
          class="group flex items-center gap-2.5 rounded-xl border px-3.5 py-3 text-left text-sm transition-all duration-200
                 {value.category_id === c.id
            ? 'border-accent/70 bg-accent/[0.07] text-white'
            : 'border-white/[0.08] text-white/60 hover:border-white/20 hover:text-white'}"
        >
          <span class="transition-colors {value.category_id === c.id ? 'text-accent' : 'text-white/35 group-hover:text-white/60'}">
            <Icon name={c.icon} size={17} />
          </span>
          <span class="truncate">{c.name}</span>
        </button>
      {/each}
    </div>
  </section>

  {#if showOptional}
    <section class="grid gap-5 sm:grid-cols-2">
      <label class="block">
        <span class="label mb-2 block">Series / subcategory</span>
        <input class="field" bind:value={value.subcategory} placeholder="e.g. Planet Earth II, Cold War" />
      </label>
      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="label mb-2 block">Year</span>
          <input
            class="field tabular"
            type="number"
            min="1880"
            max="2100"
            bind:value={value.year}
            placeholder="—"
          />
        </label>
        <label class="block">
          <span class="label mb-2 block">Language</span>
          <select class="field" bind:value={value.language}>
            {#each LANGUAGES as [code, name]}
              <option value={code}>{code ? name : '—'}</option>
            {/each}
          </select>
        </label>
      </div>
      <div class="sm:col-span-2">
        <span class="label mb-2 block">Tags</span>
        <TagInput bind:tags={value.tags} suggestions={tagSuggestions} />
      </div>
    </section>
  {/if}
</div>
