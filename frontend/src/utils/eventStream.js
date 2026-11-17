/** 按完整 SSE 事件解析，兼容 CRLF、分片 UTF-8、多行 data 与注释心跳。 */
export async function consumeEventStream(body, onEvent = () => {}) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const events = []
  function dispatch(block) {
    let type = 'message'
    const data = []
    for (const line of block.split(/\r\n|\r|\n/)) {
      if (line.startsWith('event:')) type = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length || type === 'ping') return
    const raw = data.join('\n')
    let value
    try { value = JSON.parse(raw) } catch { value = raw }
    const event = { event: type, data: value }
    events.push(event)
    onEvent(event)
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let match
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        dispatch(buffer.slice(0, match.index))
        buffer = buffer.slice(match.index + match[0].length)
      }
      if (done) { if (buffer.trim()) dispatch(buffer); break }
    }
    return events
  } finally { reader.releaseLock() }
}
