<template>
  <a class="skip-link" href="#main-content">跳转到主要内容</a>
  <router-view v-slot="{ Component, route }">
    <Transition name="route" mode="out-in">
      <component :is="Component" :key="route.matched[0]?.path" />
    </Transition>
  </router-view>
</template>

<script setup>
</script>
