---
name: audio-transcribe
description: 音视频转文字（支持说话人分离）。当用户要求把音频、录音、语音消息、视频等转成文字/文本，或提到"转文字"、"转录"、"transcribe"、"语音识别"、"会议录音整理"、"聊天录音"、"谁说的"等时使用。支持 mp3/wav/m4a/flac/ogg/aac/mp4/mkv/mov 等所有 ffmpeg 支持的格式及微信语音 silk，任意时长（无需切片），通过阿里云百炼录音文件识别接口，自动区分多个说话人，约 0.11 元/小时。
---

# 音视频转文字（说话人分离版）

阿里云百炼录音文件识别（diarization），自动区分"说话人1、说话人2"。
长音频无需本地切片，一次上传即可（DashScope 临时存储，转完自动删除）。

## 使用方法

全局命令 `asr`（PATH 由 settings.local.json 注入，cmd/PowerShell/git bash 通用）：

```bash
asr "<文件路径>"
asr "<文件路径>" --out "D:\AgentWorkspace\files\transcripts\结果.txt"
asr "<文件路径>" --no-speakers        # 关闭说话人分离，输出整段纯文本
```

可选参数：
- `--no-speakers`：关闭说话人分离，输出整段纯文本
- `--out <路径>`：保存结果到文件
- `--keep-workdir`：保留中间文件（调试用）

找不到 `asr` 命令时，回退用完整路径：
`& "C:\Users\ASUS\AppData\Local\Programs\Python\Python314\python.exe" "D:\AgentWorkspace\.claude\skills\audio-transcribe\scripts\transcribe.py" "<文件>"`

## 输出约定

- **stdout**：转写文本。多人时按 `说话人N：内容` 分段；单人时为整段纯文本
- **stderr**：进度（上传/排队/识别中）和耗时、计费估算

## 环境依赖（均已配置好，无需重复检查）

- Python314 解释器（绝对路径写在 bin 包装器里，防 uv 缓存环境劫持）
- DASHSCOPE_API_KEY：settings.local.json env + 系统用户环境变量（阿里云百炼）
- ffmpeg / ffprobe：系统 PATH
- DashScope 专属域名已内置在脚本中（ws-85b4uphg4hjd3a97.cn-beijing.maas.aliyuncs.com）

## 使用注意

1. 主模型 qwen-audio-3.1-asr-flash-filetrans 按 Token 计费（输入 25 Token/秒 × 0.8 元/百万 + 输出 2.7 元/百万），约 0.11 元/小时；脚本结束 stderr 会报估算
2. 流程耗时约音频时长的 10%~50%（上传+排队+识别），长录音先告知用户预计时间
3. 说话人分离对真人声音效果最好；ASR 与说话人编号的对应关系（谁是"说话人0"）需要结合内容判断
4. 单一说话人时脚本自动退化为整段纯文本输出（不标注说话人）
5. 转写结果如需整理成纪要/对话记录，拿到文本后再加工
6. 微信语音 silk 文件直接喂即可：脚本自动剥 0x02 头 → uv+pilk（Python3.11 临时环境）解码 24kHz pcm → ffmpeg 转 wav → 正常管线。uv 环境已缓存，无需提前安装任何东西

## IM 场景建议流程

1. 用户发来的音视频文件通常在 `D:\AgentWorkspace\temp\downloads\`
2. 运行脚本转写（长文件先告知用户"开始转写了，预计 X 分钟"）
3. 结果存 `files\transcripts\`，短结果直接贴消息，长结果发文件
4. 多人对话结果可进一步总结成"谁说了什么"的纪要
