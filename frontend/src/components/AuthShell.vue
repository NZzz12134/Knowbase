<template>
  <div class="auth-shell">
    <section class="auth-story" aria-label="关于知库">
      <RouterLink to="/login" aria-label="知库首页"><BrandLogo light :size="40" /></RouterLink>
      <div class="story-body">
        <span class="story-eyebrow">YOUR KNOWLEDGE, CONNECTED.</span>
        <h1>让知识，<br />成为你的底气。</h1>
        <p>从散落的文档，到有据可循的答案。<br />在一个专注的空间里，连接知识与思考。</p>
        <div class="knowledge-visual" aria-hidden="true">
          <div class="visual-orbit orbit-one"></div><div class="visual-orbit orbit-two"></div>
          <div class="visual-file file-one"><span>01 / DOCUMENT</span><i></i><i></i><i></i><b>知识，井然有序。</b></div>
          <div class="visual-file file-two"><span>02 / ANSWER</span><div class="visual-check">✓</div><b>每个答案，都有出处。</b><i></i><i></i></div>
          <div class="visual-label"><span></span> 从文档出发，向答案前进</div>
        </div>
      </div>
      <div class="story-footer"><span>知库 · 你的知识工作台</span><span>READ. ASK. KNOW.</span></div>
    </section>
    <main id="main-content" tabindex="-1" class="auth-content">
      <RouterLink to="/login" class="mobile-brand"><BrandLogo /></RouterLink>
      <div class="auth-form-container"><slot /></div>
      <div class="auth-bottom">专注于问题，让知识给出答案。</div>
    </main>
  </div>
</template>
<script setup>
import BrandLogo from './BrandLogo.vue'
</script>
<style scoped>
.auth-shell { min-height: 100dvh; display: grid; grid-template-columns: 47% 53%; background: #fafbf8; }
.auth-story { background: #183d30; padding: 42px 48px 26px; display: flex; flex-direction: column; color: #fff; overflow: hidden; }
.story-body { margin: auto; width: min(440px,100%); padding-top: 48px; }.story-eyebrow { font-size: 10px; letter-spacing: 2.5px; color: #bfcea8; }
h1 { font-size: clamp(38px,3.8vw,58px); line-height: 1.35; margin: 20px 0; font-weight: 520; letter-spacing: -2px; }
.story-body>p { color: #c0d0c3; font-size: 14px; line-height: 2; }
.knowledge-visual { height: 280px; position: relative; margin-top: 34px; }.visual-orbit { border: 1px solid #fff1; border-radius: 50%; position: absolute; width: 370px; height: 200px; transform: rotate(-24deg); left: 10px; top: 20px; }.orbit-two { transform: rotate(25deg); top: 28px; left: 0; }
.visual-file { position: absolute; border: 1px solid #dbe3cf; border-radius: 12px; padding: 22px; width: 218px; height: 168px; background: #f3f5e9; box-shadow: 0 16px 36px #08271b26; color: #294434; animation: appear .8s var(--ease) both; }.visual-file>span { font-size: 9px; letter-spacing: 1.3px; color: #688063; }.visual-file b { font-size: 12px; display: block; margin: 18px 0 10px; font-weight: 550; }.visual-file i { display: block; width: 100%; height: 5px; border-radius: 4px; background: #d9e0ce; margin-top: 10px; }.visual-file i:nth-of-type(2) { width: 80%; }.visual-file i:nth-of-type(3) { width: 55%; }
.file-one { left: 0; top: 5px; transform: rotate(-6deg); }.file-two { top: 75px; right: 0; background: #e1eccb; animation-delay: .12s; }.visual-check { position: absolute; top: 17px; right: 19px; width: 25px; height: 25px; display: grid; place-items: center; border-radius: 50%; background: #17634d; color: #fff; }
.visual-label { position: absolute; bottom: 0; right: 0; font-size: 10px; color: #c7d3b7; display: flex; align-items: center; gap: 8px; }.visual-label span { width: 5px; height: 5px; border-radius: 50%; background: #d5e9b0; }
.story-footer { display: flex; justify-content: space-between; gap: 15px; color: #bed0be; font-size: 10px; padding-top: 32px; }.story-footer span:last-child { letter-spacing: 1.7px; }
.auth-content { display: flex; flex-direction: column; align-items: center; padding: 48px; }.auth-form-container { width: min(370px,100%); margin: auto; padding: 40px 0; animation: appear .55s var(--ease) both; }.auth-bottom { font-size: 11px; color: var(--muted); }.mobile-brand { display: none; }
@media (min-width: 1500px) { .auth-story { padding: 55px 65px 35px; }.knowledge-visual { height: 310px; margin-top: 50px; } }
@media (max-width: 850px) { .auth-shell { grid-template-columns: 1fr; }.auth-story { display: none; }.auth-content { padding: 30px 24px; }.mobile-brand { display: inline-flex; align-self: flex-start; }.auth-form-container { padding: 56px 0; } }
</style>
