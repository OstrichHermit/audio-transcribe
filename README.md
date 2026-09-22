# audio-transcribe

音视频转文字 CLI + Claude Code Skill。基于阿里云百炼录音文件识别接口（qwen-audio-asr 系列 / paraformer），支持说话人分离，长音频免切片，原生支持微信语音 SILK 格式。

也可作为独立命令行工具使用，不一定需要 Claude Code。

## 功能特性

- **全格式输入**：mp3 / wav / m4a / aac / flac / ogg / opus / amr / wma 及 mp4 / mkv / mov 等所有 ffmpeg 支持的音视频格式（视频自动抽取音轨）
- **微信语音 SILK 原生支持**：自动识别并剥离微信 `0x02 + #!SILK_V3` 文件头，通过 [uv](https://docs.astral.sh/uv/) 临时环境调用 [pilk](https://github.com/foyoux/pilk) 解码（仅转写 silk 文件时需要 uv，其余格式零额外依赖）
- **说话人分离**：多人对话按 `说话人N：内容` 分段输出；单一说话人自动退化为整段纯文本
- **长音频免切片**：走百炼录音文件识别（filetrans）异步接口，一次上传整段处理，DashScope 临时存储转完自动删除
- **清晰的输出约定**：stdout 只输出转写文本，进度 / 耗时 / 计费估算走 stderr，方便脚本和 Agent 调用

## 依赖

- Python 3.10+（开发环境为 3.14），依赖 `dashscope`：
  ```bash
  pip install dashscope
  ```
- [ffmpeg / ffprobe](https://ffmpeg.org/) 在 PATH 中
- 阿里云百炼 API Key（[控制台](https://bailian.console.aliyun.com/) 创建），配置到环境变量：
  ```bash
  # Windows
  setx DASHSCOPE_API_KEY "sk-xxxx"
  ```
- 仅转写微信 SILK 文件时：[uv](https://docs.astral.sh/uv/)（脚本会自动创建 Python 3.11 临时环境安装 pilk，无需手动操作）

## 使用方法

```bash
python scripts/transcribe.py "<音频或视频文件路径>"
python scripts/transcribe.py "<文件>" --no-speakers   # 关闭说话人分离
python scripts/transcribe.py "<文件>" --out 结果.txt   # 保存到文件
python scripts/transcribe.py "<文件>" --keep-workdir   # 保留中间文件（调试）
```

示例：

```bash
$ python scripts/transcribe.py meeting.mp4
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

## 作为 Claude Code Skill 使用

仓库根目录的 `SKILL.md` 是 [Claude Code Agent Skill](https://code.claude.com/docs/en/skills) 定义文件，把整个仓库放到 `~/.claude/skills/audio-transcribe/`（或项目的 `.claude/skills/`）即可让 Claude 主动在语音转文字场景调用。

`bin/` 目录提供了全局命令包装器示例（`asr` / `asr.cmd`），把其中的路径改成你自己的 Python 和 skill 路径，并加入 PATH，即可在任意终端用 `asr "<文件>"` 调用。

## 可选环境变量

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 百炼 API Key（必需） |
| `DASHSCOPE_BASE_URL` | API 域名覆盖。默认指向作者的百炼**业务空间**专属域名，使用普通百炼 key 的用户请设置为 `https://dashscope.aliyuncs.com/api/v1` |
| `ASR_WORKSPACE` | 中间文件的临时根目录，默认 `D:\AgentWorkspace`（Windows 本机路径，建议按需覆盖） |

## 计费说明

- 主模型 `qwen-audio-3.1-asr-flash-filetrans` 按 Token 计费（输入 25 Token/秒 × 0.8 元/百万 + 输出 2.7 元/百万），约 **0.11 元/小时**音频
- 识别失败自动降级尝试 `paraformer-v2`
- 脚本结束会在 stderr 输出本次计费估算

## 已知限制

- 同步提交的文件大小受 DashScope 限制，超长音频依赖 filetrans 异步接口（脚本已处理，无需切片）
- 说话人编号（说话人1 / 说话人2）与真实人物的对应关系需要结合内容自行判断
- SILK 解码依赖 pilk 的预编译 wheel（cp311 及以下），通过 uv 临时环境解决，首次运行需下载环境，之后走缓存
