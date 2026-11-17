import test from 'node:test'
import assert from 'node:assert/strict'
import { consumeEventStream } from '../src/utils/eventStream.js'

test('每个事件接收后立即交给 UI，不等流结束', async () => {
  let controller
  const seen = []
  const stream = new ReadableStream({ start(c) { controller = c } })
  const encoder = new TextEncoder()
  const result = consumeEventStream(stream, event => seen.push(event))
  controller.enqueue(encoder.encode('event: token\ndata: {"content":"你好"}\n\n'))
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.deepEqual(seen, [{ event: 'token', data: { content: '你好' } }])
  controller.enqueue(encoder.encode('event: done\ndata: {"message_id":"1"}\n\n'))
  controller.close()
  assert.equal((await result).length, 2)
})

test('支持分片中文 UTF-8、CRLF、多行 data 和心跳', async () => {
  const text = ': ping\r\n\r\nevent: token\r\ndata: {"content":\r\ndata: "中文测试"}\r\n\r\nevent: done\ndata: {}\n\n'
  const bytes = new TextEncoder().encode(text)
  const stream = new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(new Uint8Array([byte])); controller.close() } })
  const events = await consumeEventStream(stream)
  assert.deepEqual(events, [{ event: 'token', data: { content: '中文测试' } }, { event: 'done', data: {} }])
})

test('保留已收到的内容并向上传递中断', async () => {
  let controller
  const seen = []
  const stream = new ReadableStream({ start(c) { controller = c } })
  const result = consumeEventStream(stream, event => seen.push(event))
  controller.enqueue(new TextEncoder().encode('event: token\ndata: {"content":"已收到"}\n\n'))
  await new Promise(resolve => setTimeout(resolve, 0))
  controller.error(new DOMException('stopped', 'AbortError'))
  await assert.rejects(result, { name: 'AbortError' })
  assert.equal(seen[0].data.content, '已收到')
})
