<template>
  <span class="brand" :class="{ 'brand--compact': compact, 'brand--light': light }" translate="no">
    <img src="/knowbase.svg" alt="" :width="size" :height="size" class="brand-mark" />
    <span v-if="!compact" class="brand-type"><strong>知库<span class="brand-divider">/</span><span class="brand-en">Knowbase</span></strong><span v-if="tagline" class="brand-tagline">{{ tagline }}</span></span>
  </span>
</template>
<script setup>
defineProps({ compact: Boolean, light: Boolean, size: { type: Number, default: 36 }, tagline: { type: String, default: '' } })
</script>
<style scoped>
.brand { display: inline-flex; align-items: center; gap: 11px; color: var(--ink); flex-shrink: 0; }
.brand-mark { border-radius: 28%; flex-shrink: 0; }.brand-type { display: flex; flex-direction: column; gap: 4px; }
.brand-type strong { font-size: 18px; font-weight: 650; letter-spacing: -.5px; white-space: nowrap; }
.brand-divider { margin: 0 8px; opacity: .24; font-weight: 400; }.brand-en { font-size: 15px; letter-spacing: -.3px; }
.brand-tagline { color: var(--muted); font-size: 10px; letter-spacing: 1.6px; }.brand--light { color: #fff; }.brand--light .brand-tagline { color: #c0d5ca; }
</style>
