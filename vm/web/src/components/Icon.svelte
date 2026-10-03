<script>
  import { ICONS } from '../lib/icons.js'

  let { name, size = 18, stroke = 1.6, class: klass = '' } = $props()
</script>

<svg
  class={klass}
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {@html ICONS[name] || ICONS.dots}
</svg>
