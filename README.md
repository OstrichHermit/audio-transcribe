# audio-transcribe

音视频转文字，支持 CLI、MCP Server 两种形态。基于阿里云百炼录音文件识别接口（qwen-audio-asr 系列 / paraformer），支持说话人分离，长音频免切片，原生支持微信语音 SILK 格式。

不依赖 Claude Code：可作为独立命令行工具，也可接入任意 MCP 客户端（Claude Desktop、Cursor 等）。

## 功能特性

- **全格式输入**：mp3 / wav / m4a / aac / flac / ogg / opus / amr / wma 及 mp4 / mkv / mov 等所有 ffmpeg 支持的音视频格式（视频自动抽取音轨）
- **微信语音 SILK 原生支持**：自动识别并剥离微信 `0x02 + #!SILK_V3` 文件头，通过 [uv](https://docs.astral.sh/uv/) 临时环境调用 [pilk](https://github.com/foyoux/pilk) 解码（仅转写 silk 文件时需要 uv，其余格式零额外依赖）
- **说话人分离**：多人对话按 `说话人N：内容` 分段输出；单一说话人自动退化为整段纯文本
- **长音频免切片**：走百炼录音文件识别（filetrans）异步接口，一次上传整段处理，DashScope 临时存储转完自动删除
- **清晰的输出约定**：stdout 只输出转写文本，进度 / 耗时 / 计费估算走 stderr，方便脚本和 Agent 调用
- **内置 MCP Server**：`audio-transcribe-mcp` 命令，手写 MCP stdio 协议（JSON-RPC 2.0），仅标准库零第三方依赖，任意 MCP 客户端即插即用

## 安装

```bash
git clone https://github.com/OstrichHermit/audio-transcribe.git
cd audio-transcribe
pip install .
```

> PyPI 发布 Coming soon，当前请从源码安装。

安装后会得到两个命令：`asr`（CLI）和 `audio-transcribe-mcp`（MCP Server）。

### 1. 安装依赖

- Python 3.10+（`pip install .` 会自动安装 dashscope 依赖）
- [ffmpeg / ffprobe](https://ffmpeg.org/) 自行安装并加入 PATH
- 仅转写微信 SILK 文件时额外需要 [uv](https://docs.astral.sh/uv/)（脚本自动创建 Python 3.11 临时环境安装 pilk，无需手动操作）

### 2. 配置 API Key

在[阿里云百炼控制台](https://bailian.console.aliyun.com/)创建 API Key，配置到环境变量：

```bash
# Windows
setx DASHSCOPE_API_KEY "sk-xxxx"

# macOS / Linux
echo 'export DASHSCOPE_API_KEY="sk-xxxx"' >> ~/.bashrc
```

默认直连百炼官方主域名，开箱即用。使用业务空间专属 key（`sk-ws-` 前缀）且分配了专属域名的用户，额外设置 `DASHSCOPE_BASE_URL` 即可（见下文[环境变量](#环境变量)）。

## 使用方法

```bash
asr "<音频或视频文件路径>"
asr "<文件>" --no-speakers   # 关闭说话人分离
asr "<文件>" --out 结果.txt   # 保存到文件
asr "<文件>" --keep-workdir   # 保留中间文件（调试）
```

示例：

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

### 微信语音（SILK）

微信语音消息文件（`*.silk`，含 `0x02 + #!SILK_V3` 头）直接作为输入传入即可，脚本自动完成剥头、pilk 解码（24kHz PCM）→ ffmpeg 封装 WAV → 正常识别管线。

## 作为 MCP Server 接入

任意支持 MCP 的客户端（Claude Code、Claude Desktop、Cursor 等）都能接入：

```bash
# Claude Code
claude mcp add audio-transcribe -- audio-transcribe-mcp
```

其他客户端在 MCP 配置 JSON 中添加（`env` 里按需配置 API Key，也可继承系统环境变量）：

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

也可以用模块方式启动：`python -m audio_transcribe_cli.mcp_server`。

接入后客户端会得到一个 `transcribe` 工具：`file_path` 必填，`speakers`（说话人分离，默认开）和 `out_path`（结果另存）可选。

## 环境变量

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 百炼 API Key（必需） |
| `DASHSCOPE_BASE_URL` | API 域名（可选）。默认 `https://dashscope.aliyuncs.com/api/v1`（官方主域名，开箱即用）；使用业务空间专属域名的用户设置为你的专属域名，例如 `https://xxxx.cn-beijing.maas.aliyuncs.com/api/v1` |
| `ASR_WORKSPACE` | 中间文件（转码 / 切片临时目录）的根目录（可选）。默认系统临时目录，转写完成自动清理 |

## 计费说明

- 主模型 `qwen-audio-3.1-asr-flash-filetrans` 按 Token 计费（输入 25 Token/秒 × 0.8 元/百万 + 输出 2.7 元/百万），约 **0.11 元/小时**音频
- 识别失败自动降级尝试 `paraformer-v2`
- 脚本结束会在 stderr 输出本次计费估算

## 已知限制

- 同步提交的文件大小受 DashScope 限制，超长音频依赖 filetrans 异步接口（脚本已处理，无需切片）
- 说话人编号（说话人1 / 说话人2）与真实人物的对应关系需要结合内容自行判断
- SILK 解码依赖 pilk 的预编译 wheel（cp311 及以下），通过 uv 临时环境解决，首次运行需下载环境，之后走缓存
