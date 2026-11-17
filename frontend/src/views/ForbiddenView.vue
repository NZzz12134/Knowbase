<template>
  <main id="main-content" tabindex="-1" class="forbidden">
    <el-result icon="warning" title="无法访问此内容" sub-title="请返回个人空间，查看自己的资料。">
      <template #extra>
        <RouterLink to="/">返回知识对话 ↗</RouterLink>
      </template>
    </el-result>
  </main>
</template>

<script setup>
</script>

<style scoped>
.forbidden { height: 100%; display: flex; align-items: center; justify-content: center; }
</style>
