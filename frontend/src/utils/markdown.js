import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'

for (const [name,language] of Object.entries({ javascript, typescript, python, json, bash, sql, xml, css })) hljs.registerLanguage(name, language)

const md = new MarkdownIt({
  html: false, // 防 XSS
  linkify: true,
  breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (_) {
        /* fallthrough */
      }
    }
    return md.utils.escapeHtml(str)
  },
})

function renderCodeBlock(code, language, env) {
  const index = env.codeBlocks.push(code) - 1
  const highlighted = md.options.highlight(code, language)
  const copied = env.copiedIndex === index
  const label = md.utils.escapeHtml(language || '纯文本')
  return `<div class="code-block"><div class="code-block-toolbar"><span class="code-language">${label}</span><button type="button" class="code-copy-button" data-code-index="${index}" aria-label="${copied ? '代码已复制' : '复制代码'}">${copied ? '已复制' : '复制代码'}</button></div><pre tabindex="0" aria-label="代码内容"><code class="hljs">${highlighted}</code></pre></div>\n`
}

md.renderer.rules.fence = (tokens, index, options, env) =>
  renderCodeBlock(tokens[index].content, tokens[index].info.trim().split(/\s+/)[0], env)
md.renderer.rules.code_block = (tokens, index, options, env) =>
  renderCodeBlock(tokens[index].content, '', env)

export function renderMarkdown(text, env = {}) {
  env.codeBlocks = []
  return md.render(text || '', env)
}
