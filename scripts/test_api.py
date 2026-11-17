"""端到端冒烟测试：登录已配置模型的账号 → 建库 → 上传 → 解析 → 账号隔离。"""
import json
import getpass
import os
import sys
import time
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000/api/v1"


def req(method, path, token=None, body=None, raw=False):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(r, data=data) as resp:
            content = resp.read()
            return resp.status, json.loads(content) if content and not raw else content
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, content.decode("utf-8", errors="replace")


def main():
    # 1. 使用已保存个人模型配置的账号。
    suffix = uuid.uuid4().hex[:10]
    username = os.environ.get("KNOWBASE_USERNAME") or input("已配置模型的知库账号：")
    password = os.environ.get("KNOWBASE_PASSWORD") or getpass.getpass("密码：")
    status, resp = req("POST", "/auth/login", body={"username": username, "password": password})
    assert status == 200, f"login failed: {resp}"
    owner_token = resp["access_token"]
    status, config = req("GET", "/me/model-config", owner_token)
    assert status == 200 and config["personal"], "请先在网页「我的模型」保存配置"
    print("[1] owner logged in with personal model configuration")

    # 2. 建知识库
    status, resp = req("POST", "/kbs", owner_token, {"name": "商品知识库", "description": "电商商品信息"})
    assert status == 201, f"create kb failed: {resp}"
    kb_id = resp["id"]
    print(f"[2] kb created: {kb_id}")

    # 3. 第二个账号功能相同，资料相互隔离。
    status, resp = req("POST", "/auth/register", body={"username": "other_" + suffix, "password": uuid.uuid4().hex})
    assert status == 201, f"register failed: {resp}"
    user_token = resp["access_token"]
    print("[3] user register OK")

    # 4. 旧地址也可用，但只返回本人的知识库。
    status, resp = req("GET", "/admin/kbs", user_token)
    assert status == 200 and resp == [], f"expected empty personal list, got {status}: {resp}"
    status, resp = req("PATCH", f"/kbs/{kb_id}", user_token, {"name": "forbidden edit"})
    assert status == 404, f"expected 404 for another account's KB: {status}"
    print("[4] equal capabilities and account isolation OK")

    # 5. 上传文档（multipart）
    boundary = "----testboundary"
    with open("scripts/testdata/products.md", "rb") as f:
        file_content = f.read()
    filename = "products.md"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode("utf-8") + file_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    r = urllib.request.Request(f"{BASE}/documents?kb_id={kb_id}", data=body, method="POST")
    r.add_header("Authorization", f"Bearer {owner_token}")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(r) as resp:
            content = json.loads(resp.read())
            print(f"[5] upload OK: {content['filename']} status={content['parse_status']}")
            doc_id = content["id"]
    except urllib.error.HTTPError as e:
        print(f"[5] upload FAILED: {e.code} {e.read().decode('utf-8', errors='replace')[:200]}")
        sys.exit(1)

    # 6. 轮询解析状态（embedding 无 key 时会 failed，验证状态机流转）
    for _ in range(10):
        time.sleep(3)
        status, resp = req("GET", f"/documents/{doc_id}", owner_token)
        assert status == 200
        ps = resp["parse_status"]
        print(f"[6] parse status: {ps} (progress={resp['parse_progress']}, error={resp['error_message']})")
        if ps in ("succeeded", "failed"):
            break
    else:
        print("[6] parse still pending after 30s")

    # 7. 分块预览
    if resp["parse_status"] == "succeeded":
        status, chunks = req("GET", f"/documents/{doc_id}/chunks?page=1&page_size=5", owner_token)
        print(f"[7] chunks total={chunks['total']}, first: {chunks['items'][0]['content'][:50] if chunks['items'] else 'N/A'}")


if __name__ == "__main__":
    main()
