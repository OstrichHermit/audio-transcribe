#!/usr/bin/env python3
"""MCP stdio server：音视频转文字工具

手写 MCP 协议（newline-delimited JSON-RPC 2.0），仅用标准库，无第三方 MCP 依赖。
复用同目录 transcribe.py 的转写流程。进度与日志全部输出到 stderr，
stdout 仅输出协议消息。

依赖：dashscope SDK、ffmpeg、DASHSCOPE_API_KEY 环境变量（同 transcribe.py）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcribe

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "audio-transcribe", "version": "1.0.0"}

TOOLS = [
    {
        "name": "transcribe",
        "description": (
            "音视频转文字，支持说话人分离。支持 mp3/wav/m4a/flac/ogg/aac/amr/wma、"
            "mp4/mkv/mov/avi/webm/flv/ts 等常见音视频格式及微信语音 silk。"
            "返回转写文本，多说话人音频按说话人分段（说话人0/1/2...）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "音频或视频文件路径"},
                "speakers": {
                    "type": "boolean",
                    "description": "是否启用说话人分离（默认 true，单说话人时输出纯文本）",
                    "default": True,
                },
                "out_path": {"type": "string", "description": "可选，结果另存为此路径"},
            },
            "required": ["file_path"],
        },
    }
]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def write(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def reply(msg_id, result):
    write({"jsonrpc": "2.0", "id": msg_id, "result": result})


def reply_error(msg_id, code, message):
    write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def run_tool(args) -> str:
    if "file_path" not in args:
        raise ValueError("缺少必填参数: file_path")
    src = Path(str(args["file_path"])).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"文件不存在: {src}")
    if src.suffix.lower() not in transcribe.SUPPORTED_EXTS:
        raise ValueError(f"不支持的格式: {src.suffix}")
    if not os.environ.get("DASHSCOPE_API_KEY"):
        raise RuntimeError("未设置 DASHSCOPE_API_KEY 环境变量")
    return transcribe.transcribe_file(
        src,
        with_speakers=bool(args.get("speakers", True)),
        out=args.get("out_path"),
    )


def handle(msg: dict):
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else PROTOCOL_VERSION
        reply(msg_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    elif method == "notifications/initialized" or method == "notifications/cancelled":
        pass
    elif method == "tools/list":
        reply(msg_id, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "transcribe":
            reply_error(msg_id, -32602, f"未知工具: {name}")
            return
        try:
            text = run_tool(args)
            reply(msg_id, {"content": [{"type": "text", "text": text}]})
        except Exception as ex:
            reply(msg_id, {
                "content": [{"type": "text", "text": f"转写失败: {ex}"}],
                "isError": True,
            })
    elif method == "ping":
        reply(msg_id, {})
    elif msg_id is not None:
        reply_error(msg_id, -32601, f"方法不存在: {method}")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    log(f"{SERVER_INFO['name']} v{SERVER_INFO['version']} 已启动（stdio，等待客户端）")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as ex:
            reply_error(None, -32700, f"JSON 解析失败: {ex}")
            continue
        handle(msg)


if __name__ == "__main__":
    main()
