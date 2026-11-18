import test from 'node:test'
import assert from 'node:assert/strict'
import { renderMarkdown } from '../src/utils/markdown.js'

test('代码块独立复制原始代码，保留缩进、换行和特殊字符，并显示语言', () => {
  const code = '<svg title="中文 & test">\n  <circle cx="20" />\n</svg>\n'
  const env = {}
  const html = renderMarkdown('示例\n\n```html\n' + code + '```\n\n```unknown\nx < y\n```', env)
  assert.deepEqual(env.codeBlocks, [code, 'x < y\n'])
  assert.equal((html.match(/class="code-copy-button"/g) || []).length, 2)
  assert.ok(html.includes('data-code-index="1"'))
  assert.ok(html.includes('hljs-tag'))
  assert.ok(!html.includes('<svg'))
  assert.ok(html.includes('<span class="code-language">html</span>'))
  assert.ok(html.includes('<span class="code-language">unknown</span>'))
})

test('未闭合的流式代码块和缩进代码块也可复制，语言信息不能注入 HTML', () => {
  const env = {}
  const html = renderMarkdown('```bad"><img/src=x/onerror=alert(1)>\n<script>alert(1)</script>', env)
  assert.deepEqual(env.codeBlocks, ['<script>alert(1)</script>'])
  assert.ok(!html.includes('<img'))
  assert.ok(!html.includes('<script>'))
  assert.ok(html.includes('&lt;script&gt;'))
  const plain = renderMarkdown('    line1\n    line2\n', env)
  assert.deepEqual(env.codeBlocks, ['line1\nline2\n'])
  assert.ok(plain.includes('<span class="code-language">纯文本</span>'))
})
