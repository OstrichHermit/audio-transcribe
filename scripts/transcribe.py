#!/usr/bin/env python3
"""音视频转文字（带说话人分离）：阿里云百炼录音文件识别 + diarization

流程：ffmpeg 统一音频 → DashScope 临时存储上传 → 录音文件识别（说话人分离）→ 轮询取结果
stdout 输出转写文本，stderr 输出进度信息。

依赖：dashscope SDK（Python314 环境）、ffmpeg、DASHSCOPE_API_KEY 环境变量。
微信语音 SILK 格式：自动剥 0x02 前缀 → uv+pilk 解码为 wav（pilk 仅 cp311，走 uv 临时环境）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import dashscope
from dashscope.audio.asr import Transcription

# 业务空间专属域名（sk-ws- 前缀的业务空间 key 必需）。普通百炼 key 请设置环境变量
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1 覆盖
dashscope.base_http_url = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://ws-85b4uphg4hjd3a97.cn-beijing.maas.aliyuncs.com/api/v1",
)

# 中间文件存放的临时根目录，可通过 ASR_WORKSPACE 环境变量覆盖
WORKSPACE = Path(os.environ.get("ASR_WORKSPACE", r"D:\AgentWorkspace"))
MODEL = "qwen-audio-3.1-asr-flash-filetrans"
FALLBACK_MODELS = ["paraformer-v2"]
SUPPORTED_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".amr", ".wma",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v", ".wmv",
    ".silk",
}

# uv 用于 SILK 解码（pilk 仅提供 cp311 及以下 wheel，本机 Python314 装不上）
_UV_FALLBACK = Path(r"C:\Users\ASUS\AppData\Local\Programs\Python\Python314\Scripts\uv.exe")


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(str(c) for c in cmd)}\n{r.stderr[-2000:]}")
    return r.stdout.strip()


def prepare_audio(src: Path, workdir: Path) -> Path:
    """视频抽音轨、统一转 16kHz 单声道 mp3（小体积、通用格式）"""
    audio = workdir / "audio.mp3"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio])
    return audio


def decode_silk(src: Path, workdir: Path) -> Path:
    """微信语音 SILK 解码为 wav：剥 0x02 前缀 → pilk 解码 24kHz mono pcm → ffmpeg 封装

    微信 silk 头部为 0x02 + "#!SILK_V3"；pilk.decode 输出 24kHz 16bit 单声道 pcm。
    """
    data = src.read_bytes()
    if data[:10] == b"\x02#!SILK_V3":
        data = data[1:]
    if data[:9] != b"#!SILK_V3":
        raise RuntimeError("不是有效的 SILK 文件（头部不匹配 #!SILK_V3）")
    clean_silk = workdir / "clean.silk"
    clean_silk.write_bytes(data)

    uv_exe = shutil.which("uv") or (_UV_FALLBACK if _UV_FALLBACK.exists() else None)
    if uv_exe is None:
        raise RuntimeError("未找到 uv 可执行文件，无法解码 SILK")
    eprint("  SILK 格式：pilk 解码中（uv 临时环境，首次运行较慢）...")
    pcm = workdir / "audio.pcm"
    code = f"import pilk\npilk.decode(r'{clean_silk}', r'{pcm}')\n"
    run([uv_exe, "run", "--python", "3.11", "--with", "pilk", "python", "-c", code])
    if not pcm.exists() or pcm.stat().st_size == 0:
        raise RuntimeError("SILK 解码失败：pcm 输出为空")

    wav = workdir / "silk_audio.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm, wav])
    return wav


def upload_to_dashscope(audio: Path):
    """上传到 DashScope 托管存储，返回 (file_id, 签名下载URL)"""
    f = dashscope.Files.upload(file_path=str(audio), purpose="file-extract",
                               api_key=dashscope.api_key)
    if f.status_code != 200:
        raise RuntimeError(f"上传失败: {f.code} {f.message}")
    file_id = f.output["uploaded_files"][0]["file_id"]
    g = dashscope.Files.get(file_id=file_id, api_key=dashscope.api_key)
    if g.status_code != 200:
        raise RuntimeError(f"获取下载链接失败: {g.code} {g.message}")
    return file_id, g.output["url"]


def submit_task(url: str):
    """提交识别任务，依次尝试主模型和备选模型"""
    models = [MODEL] + FALLBACK_MODELS
    last = None
    for model in models:
        try:
            resp = Transcription.async_call(model=model, file_urls=[url],
                                            diarization_enabled=True)
        except Exception as ex:
            last = f"{model}: {ex}"
            continue
        if resp.status_code == 200:
            eprint(f"识别模型: {model}")
            return model, resp.output.task_id
        last = f"{model}: {resp.status_code} {resp.code} {resp.message}"
    raise RuntimeError(f"所有识别模型提交失败: {last}")


def wait_result(task_id: str, audio_seconds: float, timeout: float = None):
    """轮询任务直到完成。filetrans 排队+识别一般数十秒到数分钟"""
    if timeout is None:
        timeout = max(180, min(audio_seconds * 2, 3600))
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        r = Transcription.fetch(task=task_id)
        if r.output.task_status == "SUCCEEDED":
            t_url = getattr(r.output, "transcription_url", None)
            if not t_url:
                t_url = r.output["results"][0]["transcription_url"]
            with urllib.request.urlopen(t_url, timeout=60) as fh:
                return json.load(fh)
        if r.output.task_status == "FAILED":
            code = ""
            msg = ""
            try:
                code = r.output["code"]
                msg = r.output["message"]
            except Exception:
                pass
            raise RuntimeError(f"识别任务失败: {code} {msg}")
        eprint(f"  识别中... {time.time() - t0:.0f}s")
    raise RuntimeError("等待识别结果超时")


def format_text(data: dict, with_speakers: bool) -> str:
    """按说话人分段输出；若只有单一说话人则输出整段纯文本"""
    transcripts = data.get("transcripts", [])
    if not with_speakers:
        return "\n".join(tr.get("text", "").strip() for tr in transcripts if tr.get("text"))

    speakers_used = set()
    all_sentences = []
    for tr in transcripts:
        all_sentences.extend(tr.get("sentences", []))
        for s in tr.get("sentences", []):
            if s.get("speaker_id") is not None:
                speakers_used.add(s["speaker_id"])

    if len(speakers_used) < 2:
        return "\n".join(tr.get("text", "").strip() for tr in transcripts if tr.get("text"))

    lines = []
    cur_spk, buf = None, []
    for s in all_sentences:
        spk = s.get("speaker_id")
        if spk != cur_spk:
            if buf:
                lines.append(f"说话人{cur_spk}：{''.join(buf)}")
            cur_spk, buf = spk, []
        buf.append(s["text"])
    if buf:
        lines.append(f"说话人{cur_spk}：{''.join(buf)}")
    return "\n".join(lines)


def transcribe_file(src: Path, with_speakers: bool = True, out: str = None,
                    keep_workdir: bool = False) -> str:
    """核心流程：预处理 → 上传 → 识别 → 格式化，返回转写文本（CLI 与 MCP 共用）"""
    tmp_root = WORKSPACE / "temp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="asr_", dir=tmp_root))
    file_id = None
    t0 = time.time()

    try:
        eprint(f"[1/4] ffmpeg 预处理: {src.name}")
        if src.suffix.lower() == ".silk":
            src = decode_silk(src, workdir)
        audio = prepare_audio(src, workdir)
        dur_out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=nw=1:nk=1", audio])
        dur = float(dur_out)
        eprint(f"[2/4] 上传音频（{dur / 60:.1f} 分钟）...")
        file_id, dl_url = upload_to_dashscope(audio)

        eprint("[3/4] 提交识别任务...")
        _, task_id = submit_task(dl_url)
        result = wait_result(task_id, dur)

        text = format_text(result, with_speakers=with_speakers)
        eprint(f"[4/4] 完成，耗时 {time.time() - t0:.0f}s，音频 {dur / 60:.1f} 分钟"
               f"（计费约 {dur / 3600 * 0.11:.2f} 元，按 3.1 Token 计费估算）")

        if out:
            out_path = Path(out).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text + "\n", encoding="utf-8")
            eprint(f"已保存: {out_path}")
        return text
    finally:
        if file_id:
            try:
                dashscope.Files.delete(file_id=file_id, api_key=dashscope.api_key)
            except Exception:
                pass
        if keep_workdir:
            eprint(f"中间文件保留: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="音视频转文字（阿里云百炼，支持说话人分离）")
    ap.add_argument("input", help="音频或视频文件路径")
    ap.add_argument("--no-speakers", action="store_true", help="关闭说话人分离，输出纯文本")
    ap.add_argument("--out", default=None, help="结果保存路径（默认只打印）")
    ap.add_argument("--keep-workdir", action="store_true", help="保留中间文件（调试用）")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        eprint(f"文件不存在: {src}")
        sys.exit(1)
    if src.suffix.lower() not in SUPPORTED_EXTS:
        eprint(f"不支持的格式: {src.suffix}")
        sys.exit(1)
    if not os.environ.get("DASHSCOPE_API_KEY"):
        eprint("未设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    print(transcribe_file(src, with_speakers=not args.no_speakers,
                          out=args.out, keep_workdir=args.keep_workdir))


if __name__ == "__main__":
    main()
