# audio-transcribe-cli-mcp

**Audio/video transcription in both CLI and MCP Server flavors: speaker diarization, long-audio support with no manual splitting, and native WeChat SILK decoding.**

音视频转文字，支持 CLI、MCP Server 两种形态：说话人分离，长音频免切片，原生支持微信语音 SILK 格式。

English | [简体中文](README.md)

Powered by the Alibaba Cloud Bailian file-transcription API (qwen-audio-asr series / paraformer). No Claude Code dependency: use it as a standalone command-line tool, or plug it into any MCP client (Claude Desktop, Cursor, etc.).

## Features

- **All-format input**: every ffmpeg-supported audio/video format — mp3 / wav / m4a / aac / flac / ogg / opus / amr / wma and mp4 / mkv / mov etc. (audio track auto-extracted from video)
- **Native WeChat SILK support**: auto-detects and strips the WeChat `0x02 + #!SILK_V3` header, decoding via [pilk](https://github.com/foyoux/pilk) in a [uv](https://docs.astral.sh/uv/) ephemeral environment (uv is only needed for SILK files; all other formats are dependency-free)
- **Speaker diarization**: multi-speaker conversations are segmented as `说话人N：内容` (Speaker N: content); a single speaker degrades gracefully to plain text
- **Long audio without splitting**: uses the Bailian file-transcription (filetrans) async API — upload once, processed whole; DashScope temp storage is deleted automatically after transcription
- **Clean output contract**: stdout carries transcription text only; progress / timing / cost estimates go to stderr — script- and agent-friendly
- **Built-in MCP Server**: the `audio-transcribe-mcp` command, hand-written MCP stdio protocol (JSON-RPC 2.0), stdlib only with zero third-party deps — plug and play with any MCP client

## Install

```bash
pip install audio-transcribe-cli-mcp
```

Or install from source:

```bash
git clone https://github.com/OstrichHermit/audio-transcribe-cli-mcp.git
cd audio-transcribe-cli-mcp
pip install .
```

You get two commands: `asr` (CLI) and `audio-transcribe-mcp` (MCP Server).

### Install as an Agent Skill (optional)

This repo ships with an Agent Skill (`skills/audio-transcribe-cli-mcp/SKILL.md`). Copy it into your AI agent's skills directory so the agent picks up the tool automatically. Claude Code example:

```bash
cp -r skills/audio-transcribe-cli-mcp ~/.claude/skills/audio-transcribe-cli-mcp
```

### 1. Dependencies

- Python 3.10+ (`pip install .` pulls in dashscope automatically)
- [ffmpeg / ffprobe](https://ffmpeg.org/) installed separately and on PATH
- [uv](https://docs.astral.sh/uv/) only for transcribing WeChat SILK files (the script auto-creates a Python 3.11 ephemeral environment for pilk — no manual steps)

### 2. Configure the API Key

Create an API Key in the [Alibaba Cloud Bailian console](https://bailian.console.aliyun.com/) and set it as an environment variable:

```bash
# Windows
setx DASHSCOPE_API_KEY "sk-xxxx"

# macOS / Linux
echo 'export DASHSCOPE_API_KEY="sk-xxxx"' >> ~/.bashrc
```

It talks to the official Bailian primary domain out of the box. If you use a workspace-scoped key (`sk-ws-` prefix) with a dedicated domain, additionally set `DASHSCOPE_BASE_URL` (see [Environment variables](#environment-variables)).

## Usage

```bash
asr "<audio or video file>"
asr "<file>" --no-speakers   # disable speaker diarization
asr "<file>" --out result.txt # save to file
asr "<file>" --keep-workdir   # keep intermediate files (debug)
```

Example:

```bash
$ asr meeting.mp4
[1/4] ffmpeg 预处理: meeting.mp4
[2/4] 上传音频（32.5 分钟）...
[3/4] 提交识别任务...
识别模型: qwen-audio-3.1-asr-flash-filetrans
  识别中... 45s
[4/4] 完成，耗时 78s，音频 32.5 分钟（计费约 0.06 元，按 3.1 Token 计费估算）
说话人1：大家好，今天我们讨论一下项目排期……
说话人2：好的，我先说下我这边的情况……
```

### WeChat voice messages (SILK)

WeChat voice message files (`*.silk`, with the `0x02 + #!SILK_V3` header) can be passed in directly — the script strips the header, decodes via pilk (24 kHz PCM), wraps into WAV with ffmpeg, then runs the normal pipeline.

## Use as an MCP Server

Any MCP-capable client (Claude Code, Claude Desktop, Cursor, etc.) can attach it:

```bash
# Claude Code
claude mcp add audio-transcribe -- audio-transcribe-mcp
```

Other clients: add to your MCP config JSON (set the API key in `env` as needed, or inherit system environment variables):

```json
{
  "mcpServers": {
    "audio-transcribe": {
      "command": "audio-transcribe-mcp",
      "env": {
        "DASHSCOPE_API_KEY": "sk-xxxx"
      }
    }
  }
}
```

Module launch also works: `python -m audio_transcribe_cli.mcp_server`.

Once attached, the client gets one `transcribe` tool: `file_path` required; `speakers` (diarization, on by default) and `out_path` (save result to a file) optional.

## Environment variables

| Variable | Description |
|------|------|
| `DASHSCOPE_API_KEY` | Bailian API Key (required) |
| `DASHSCOPE_BASE_URL` | API domain (optional). Defaults to `https://dashscope.aliyuncs.com/api/v1` (official primary domain, works out of the box); workspace users with a dedicated domain should set it to yours, e.g. `https://xxxx.cn-beijing.maas.aliyuncs.com/api/v1` |
| `ASR_WORKSPACE` | Root directory for intermediate files (transcoding / splitting temp dirs, optional). Defaults to the system temp dir; cleaned up automatically after transcription |

## Billing

- The main model `qwen-audio-3.1-asr-flash-filetrans` is token-billed (input 25 tokens/s × ¥0.8/M + output ¥2.7/M), roughly **¥0.11/hour** of audio
- On recognition failure it automatically falls back to `paraformer-v2`
- A cost estimate for the run is printed to stderr at the end

## Known limitations

- Synchronously submitted files are size-capped by DashScope; extra-long audio relies on the filetrans async API (handled automatically, no manual splitting)
- The mapping between speaker numbers (说话人1 / 说话人2) and real people needs to be judged from the content
- SILK decoding depends on pilk's prebuilt wheels (cp311 and below), solved via a uv ephemeral environment — the first run downloads it, afterwards it's cached
