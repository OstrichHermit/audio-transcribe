---
name: audio-transcribe-cli-mcp
description: 音视频转文字（支持说话人分离）。当用户要求把音频、录音、语音消息、视频等转成文字/文本，或提到"转文字"、"转录"、"transcribe"、"语音识别"、"会议录音整理"、"聊天录音"、"谁说的"等时使用。支持 mp3/wav/m4a/flac/ogg/aac/mp4/mkv/mov 等所有 ffmpeg 支持的格式及微信语音 silk，任意时长（无需切片），通过阿里云百炼录音文件识别接口，自动区分多个说话人，约 0.11 元/小时。
---

# 音视频转文字（说话人分离版）

阿里云百炼录音文件识别（diarization），自动区分"说话人1、说话人2"。
长音频无需本地切片，一次上传即可（DashScope 临时存储，转完自动删除）。

## 安装

```bash
pip install audio-transcribe-cli-mcp
```

装完得到两个命令：`asr`（命令行）和 `audio-transcribe-mcp`（MCP Server）。

## 使用方法

```bash
asr "<音视频文件路径>"
asr "<文件路径>" --out "结果.txt"          # 保存结果到文件
asr "<文件路径>" --no-speakers             # 关闭说话人分离，输出整段纯文本
asr "<文件路径>" --timestamps              # 逐句输出起止时间戳（会议纪要定位原音频用）
```

可选参数：
- `--no-speakers`：关闭说话人分离，输出整段纯文本
- `--timestamps`：逐句输出 SRT 风格起止时间戳，多说话人时带说话人编号（可配合 `--no-speakers`）
- `--out <路径>`：保存结果到文件
- `--keep-workdir`：保留中间文件（调试用）

## 输出约定

- **stdout**：转写文本。多人时按 `说话人N：内容` 分段；单人时为整段纯文本
- **stderr**：进度（上传/排队/识别中）和耗时、计费估算
- **`--timestamps` 模式**：每句一行，格式 `[HH:MM:SS,mmm -> HH:MM:SS,mmm] 说话人N：内容`

MCP 工具 `transcribe` 对应参数为 `timestamps`（boolean，默认 false）。

## 环境依赖

- Python 3.10+（dashscope SDK 由 pip 自动安装）
- ffmpeg / ffprobe 在系统 PATH 中
- DASHSCOPE_API_KEY 环境变量：阿里云百炼（bailian.console.aliyun.com）的 API Key
- 需要转写微信语音 silk 时，另需系统 PATH 里有 uv（首次运行自动搭临时环境，会慢一些）
- 业务空间（sk-ws- 前缀）API Key 用户请额外设置 DASHSCOPE_BASE_URL 环境变量

## 计费与耗时

- 按 Token 计费，约 0.11 元/小时，走你自己的百炼账户；脚本结束会在 stderr 报估算
- 流程耗时约为音频时长的 10%~50%（上传+排队+识别）

## 使用注意

1. 说话人分离对真人声音效果最好；ASR 与说话人编号的对应关系（谁是"说话人0"）需要结合内容判断
2. 单一说话人时自动退化为整段纯文本输出（不标注说话人）
3. 微信语音 silk 文件直接喂即可：自动剥 0x02 头解码为 wav，再走正常管线
4. 转写结果如需整理成纪要/对话记录，拿到文本后再加工；需要回原音频核对时用 `--timestamps` 拿时间戳
