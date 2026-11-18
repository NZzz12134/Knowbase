"""分离模型显式返回的思考与正文；兼容分片的前导 <think> 标签。"""
MAX_REASONING_CHARS = 200_000


def text_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(block if isinstance(block, str) else block.get("text", "")
                   for block in content if isinstance(block, str) or isinstance(block, dict) and block.get("type") == "text")


def reasoning_content(chunk):
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = chunk.additional_kwargs.get(key)
        if isinstance(value, str) and value:
            return value
    if isinstance(chunk.content, list):
        return "".join(block.get("text") or block.get("thinking") or "" for block in chunk.content
                       if isinstance(block, dict) and block.get("type") in ("reasoning", "thinking", "reasoning_content"))
    return ""


class ThinkTagSplitter:
    def __init__(self):
        self.state = "prefix"
        self.pending = ""

    def feed(self, text):
        self.pending += text
        if self.state == "prefix":
            prefix = self.pending.lstrip()
            if not prefix or "<think>".startswith(prefix):
                if prefix != "<think>":
                    return "", ""
            if prefix.startswith("<think>"):
                self.pending = prefix[len("<think>"):]
                self.state = "thinking"
            else:
                self.state = "answer"
        if self.state == "thinking":
            marker = "</think>"
            if marker in self.pending:
                thought, self.pending = self.pending.split(marker, 1)
                self.state = "answer"
                answer, self.pending = self.pending, ""
                return answer, thought
            keep = max((size for size in range(1, len(marker)) if self.pending.endswith(marker[:size])), default=0)
            thought = self.pending[:-keep] if keep else self.pending
            self.pending = self.pending[-keep:] if keep else ""
            return "", thought
        answer, self.pending = self.pending, ""
        return answer, ""

    def finish(self):
        text, self.pending = self.pending, ""
        return ("", text) if self.state == "thinking" else (text, "")
