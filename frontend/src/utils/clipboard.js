export async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return } catch (_) { /* 使用兼容方式重试 */ }
  }
  // 局域网 HTTP 部署可能没有 Clipboard API。
  const previousFocus = document.activeElement
  const input = document.createElement('textarea')
  input.value = text
  input.readOnly = true
  input.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0;font-size:16px'
  document.body.append(input)
  try {
    input.select()
    if (!document.execCommand('copy')) throw new Error('copy_failed')
  } finally {
    input.remove()
    previousFocus?.focus({ preventScroll: true })
  }
}
