"""SSE 流式问答端点。

事件协议：
    event: citations  data: {"citations":[{id,text,filename,page,row_start,row_end,heading_path,score}], "mode": "hybrid+rerank"}
    event: token      data: {"content": "..."}   ×N
    event: done       data: {"message_id": "...", "usage": {...}}
    event: error      data: {"message": "..."}
"""
import asyncio
import logging
import uuid
import anyio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from app.core.deps import get_current_user, get_db, get_session_or_404
from app.core.exceptions import BusinessError
from app.core.rate_limit import limiter, user_or_ip_key
from app.models import ChatSession, Citation, Feedback, Message, User
from app.services.message_order import message_order
from app.schemas.chat_schema import ChatIn
from app.services import message_service
from app.services.personal_access import active_kb_ids, retrieval_scope
from app.services.rag.chain import run_qa_stream
from app.utils.sse import sse_event, sse_ping

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# 全局并发信号量：防 LLM API 打爆
_llm_semaphore = asyncio.Semaphore(4)


@router.post("/chat/stream")
@limiter.limit("10/minute", key_func=user_or_ip_key)
async def chat_stream(
    request: Request,
    data: ChatIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session_or_404(db, data.session_id, user.id)
    from app.services.model_config_service import load_model_settings
    model_settings = await load_model_settings(user.id)
    kb_ids = await active_kb_ids(db, user.id, session.kb_id)

    async def event_generator():
        await _llm_semaphore.acquire()
        assistant_msg = None
        full_content: list[str] = []
        next_event_task = None
        try:
            await db.execute(select(ChatSession.id).where(ChatSession.id == data.session_id).with_for_update())
            recent = list((await db.execute(select(Message).where(Message.session_id == data.session_id)
                .order_by(*message_order(descending=True)).limit(2).with_for_update())).scalars())
            if recent and recent[0].status == "generating":
                raise BusinessError("answer_busy", "此会话仍在生成回答，请先停止或稍后重试", 409)
            excluded = ()
            if data.retry_message_id:
                if len(recent) != 2 or recent[0].id != data.retry_message_id or recent[0].role != "assistant" or recent[1].role != "user":
                    raise BusinessError("invalid_retry", "只能重新生成当前会话的最后一条回答", 409)
                assistant_msg = recent[0]
                excluded = (recent[0].id, recent[1].id)
                question = recent[1].content
            else:
                question = data.question
            # 历史（先取，不含本条提问）
            history = await message_service.get_recent_history(db, data.session_id, limit=6, exclude_ids=excluded)

            # 落 user message + assistant 占位
            if assistant_msg is None:
                await message_service.create_user_message(db, data.session_id, question)
                assistant_msg = await message_service.create_assistant_placeholder(db, data.session_id)
            else:
                await db.execute(delete(Citation).where(Citation.message_id == assistant_msg.id))
                await db.execute(delete(Feedback).where(Feedback.message_id == assistant_msg.id))
                assistant_msg.content, assistant_msg.status, assistant_msg.error_message = "", "generating", None
                assistant_msg.token_usage = None
            await message_service.touch_session(db, data.session_id)
            await db.commit()
            message_id = str(assistant_msg.id)
            yield sse_event("start", {"message_id": message_id})

            stream = run_qa_stream(session.kb_id, question, history, refresh=bool(data.retry_message_id))
            # 心跳实现：用 asyncio.wait 限时等待下一事件，超时只发 ping、不取消
            # 生成器任务（asyncio.timeout 会取消内部 await，导致 generator 报废）
            next_event_task = asyncio.ensure_future(stream.__anext__())
            while True:
                done, _ = await asyncio.wait([next_event_task], timeout=15)
                if not done:
                    # 15 秒无事件：心跳保活（防 nginx/代理 read_timeout 掐断长流）
                    if await request.is_disconnected():
                        await message_service.finalize_message(
                            db, assistant_msg, "".join(full_content), status="stopped"
                        )
                        return
                    yield sse_ping()
                    continue
                try:
                    event, payload = next_event_task.result()
                except StopAsyncIteration:
                    break

                if await request.is_disconnected():
                    await message_service.finalize_message(
                        db, assistant_msg, "".join(full_content), status="stopped"
                    )
                    return

                if event == "citations":
                    assistant_msg.token_usage = {"answer_mode": payload.get("answer_mode", "knowledge" if payload["citations"] else "general")}
                    await message_service.save_citations(db, assistant_msg.id, payload["citations"])
                    yield sse_event("citations", payload)
                elif event == "token":
                    full_content.append(payload["content"])
                    yield sse_event("token", payload)
                elif event == "usage":
                    assistant_msg.token_usage = {**(assistant_msg.token_usage or {}), **payload}
                next_event_task = asyncio.ensure_future(stream.__anext__())

            await message_service.finalize_message(
                db, assistant_msg, "".join(full_content), status="completed"
            )
            yield sse_event("done", {"message_id": message_id})

            # 异步生成会话标题（首条消息）
            await message_service.auto_title_session(db, data.session_id, question)

        except asyncio.CancelledError:
            if assistant_msg is not None:
                # The ASGI disconnect scope is cancelled; shield the final DB write.
                with anyio.CancelScope(shield=True):
                    await message_service.finalize_message(
                        db, assistant_msg, "".join(full_content), status="stopped"
                    )
            raise
        except Exception as exc:
            logger.exception("chat stream failed")
            if assistant_msg is not None:
                await message_service.finalize_message(
                    db, assistant_msg, "".join(full_content), status="failed", error=str(exc)[:500]
                )
            yield sse_event("error", {"message": exc.message if isinstance(exc, BusinessError) else "生成失败，请稍后重试；也可到我的模型检查连接。"})
        finally:
            if next_event_task is not None and not next_event_task.done():
                next_event_task.cancel()
                try:
                    with anyio.CancelScope(shield=True):
                        await next_event_task
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
            _llm_semaphore.release()

    async def configured_event_generator():
        from app.services.model_config_service import model_settings_scope
        try:
            with model_settings_scope(model_settings), retrieval_scope(user.id, kb_ids):
                async for event in event_generator():
                    yield event
        except BusinessError as exc:
            yield sse_event("error", {"message": exc.message})
        except Exception:
            logger.exception("configured chat stream failed")
            yield sse_event("error", {"message": "模型配置加载失败，请检查「我的模型」设置或稍后重试"})

    return StreamingResponse(
        configured_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
