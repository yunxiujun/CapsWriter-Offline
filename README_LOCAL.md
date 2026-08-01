# CapsWriter-Offline 本地维护说明

## 本地 LLM 知识库

- 每个角色可设置 `enable_knowledge_base = True` 开启独立知识库。
- 默认目录为 `LLM知识库/<角色主名称>`，支持 TXT、MD、Markdown 和子目录。
- 知识库关闭时不扫描文件，不影响其他角色。
- 模型回答后自动附加命中的完整原文段落，附录不经过模型改写。
- 详细操作见 `docs/LLM本地知识库如何使用.md`。

这份文档只说明本地 fork 的维护方式。原项目说明仍见 `readme.md`。

## 当前目录分工

- 运行目录：`D:\AI\CapsWriter-Offline`
  - 日常双击 `start_server.exe` / `start_client.exe` 使用。
  - 里面有模型、日志、exe、个人 `LLM\*.py` 角色和 API key。
  - 不适合作为干净 Git 提交目录。

- 维护目录：`D:\AI\CapsWriter-Offline-git`
  - 用来提交、推送、合并官方更新。
  - 当前分支：`my-local-adapt`
  - 个人 fork：`origin = https://github.com/yunxiujun/CapsWriter-Offline.git`
  - 官方上游：`upstream = https://github.com/HaujetZhao/CapsWriter-Offline.git`
  - `upstream` 的 push 已禁用，避免误推官方仓库。

## 已加入的本地功能

- xAI/Grok Responses API 支持，可用于 `web_search` 工具。
- MiniMax 大陆区 Token Plan Web Search 支持。角色通过高级选项启用后，程序先调用
  `https://api.minimaxi.com/v1/coding_plan/search`，再把实时结果交给 MiniMax 模型回答。
- Toast 支持 `toast_position_y` 初始屏幕 y 坐标。
- Toast 右侧按钮：
  - `固`：固定当前窗口位置。
  - `移`：取消固定，允许移动。
  - `消/留`：切换自动消失或保留到 `ESC`。
- `固/移` 和 `消/留` 会保存到运行目录的 `.toast_state.json`，重启后仍保留。
- `.toast_state.json` 已加入 `.gitignore`，不会提交。
- LLM 读取选区改为唯一标记加轮询等待，改善浏览器 `Ctrl+A` 整页复制较慢、
  或选中文字与原剪贴板内容相同时误判为空的问题。
- 命中非默认角色唤醒词后，语音里出现 `剪贴板`、`剪切板`、`剪贴版`、
  `剪切版` 时，会直接把当前剪贴板文字加入 LLM 上下文。
- 按住识别快捷键录音时，可临时静音 Windows 默认输出设备；录音完成、取消或
  客户端退出时恢复录音前的静音状态。
- 运行目录已同步官方 v2.6 发布后的 12 项修复至 `upstream/master` 的
  `7d7fac3`，包括热词检索提速、黑名单、Unicode 字母、正负数、斤两、
  麦克风权限提示和模型目录检查；发生重叠时保留本地 ITN 规则。

## 角色文件里的本地配置

所有运行目录的 `D:\AI\CapsWriter-Offline\LLM\*.py` 都只保留这类注释配置：

```python
# toast_position_y = 420                 # 可选：Toast 窗口初始屏幕高度/y 坐标（-1 表示屏幕中间）
```

需要某个角色固定初始高度位置时，只删除这一行前面的 `#`。

固定/移动、自动消失/保留不要再写进 `LLM\*.py`，在 Toast 浮动窗口右侧按钮里设置即可。

剪贴板关键词功能默认启用。使用时先把正文复制到剪贴板，例如先按
`Ctrl+A`、`Ctrl+C`，再说“联网助理，根据剪贴板内容总结这篇文章”。
如果只选中文字、不说剪贴板关键词，程序仍会自动模拟 `Ctrl+C` 获取选区。

每个角色可以取消注释并单独调整：

```python
# selection_copy_timeout = 0.8
# enable_read_clipboard = True
# clipboard_keywords = ('剪贴板', '剪切板', '剪贴版', '剪切版')
# clipboard_max_length = 20000
# prompt_prefix_clipboard = '剪贴板内容：'
```

录音时静音是客户端全局功能，在 `config_client.py` 中调整：

```python
mute_system_audio_while_recording = True  # False 表示关闭
mute_restore_delay = 0.08                 # 停止录音后恢复声音的延迟（秒）
```

该功能只切换静音状态，不修改音量数值。电脑原本已静音时，录音结束后仍保持静音。

MiniMax 联网角色使用运行目录的个人角色文件配置，不要提交该文件：

```python
provider = 'minimax'
api_url = 'https://api.minimaxi.com/v1'
api_key = ''  # 自行填写 Token Plan Key
model = 'MiniMax-M3'
extra_options = {
    'minimax_web_search': True,
    'minimax_search_max_results': 8,
    'minimax_search_timeout': 20,
}
```

这些 `minimax_*` 字段是 CapsWriter 本地控制项，请求模型前会被移除，不会误传给
Chat Completions。搜索失败或没有有效结果时会直接报错，不会退化成未联网回答。

## 官方更新后怎么合流

在维护目录执行：

```powershell
cd D:\AI\CapsWriter-Offline-git
git checkout my-local-adapt
git fetch upstream master
git merge upstream/master
```

如果没有冲突，继续：

```powershell
python -m py_compile LLM\__init__.py core\client\llm\llm_role_config.py core\client\llm\llm_output_toast.py core\ui\toast_manager.py core\ui\toast.py core\ui\toast_base.py core\ui\toast_text.py core\ui\toast_label.py
git push
```

如果出现冲突：

1. 先看冲突文件：

```powershell
git status
```

2. 优先保护这些本地功能相关文件里的改动：

```text
core/client/llm/llm_constants.py
core/client/llm/llm_client_pool.py
core/client/llm/llm_processor.py
core/client/llm/llm_minimax_search.py
core/client/llm/llm_role_config.py
core/client/llm/llm_get_selection.py
core/client/llm/llm_handler.py
core/client/llm/llm_message_builder.py
core/client/llm/llm_role_formatter.py
core/client/llm/llm_output_toast.py
core/client/audio/system_audio_mute.py
core/client/shortcut/task.py
core/client/app.py
config_client.py
core/ui/toast_manager.py
core/ui/toast.py
core/ui/toast_base.py
core/ui/toast_text.py
core/ui/toast_label.py
LLM/__init__.py
```

3. 手动编辑冲突文件，确认没有 `<<<<<<<`、`=======`、`>>>>>>>` 后：

```powershell
rg "<<<<<<<|=======|>>>>>>>" .
git add <已解决的文件>
git commit
python -m py_compile LLM\__init__.py core\client\llm\llm_role_config.py core\client\llm\llm_output_toast.py core\ui\toast_manager.py core\ui\toast.py core\ui\toast_base.py core\ui\toast_text.py core\ui\toast_label.py
git push
```

## 同步到正在使用的运行目录

合流、提交、推送成功后，把维护目录里的源码同步到运行目录。

只同步源码，不同步模型、日志、exe、个人 key。

常用同步命令：

```powershell
$src = 'D:\AI\CapsWriter-Offline-git'
$dst = 'D:\AI\CapsWriter-Offline'
$files = @(
  'LLM\__init__.py',
  'core\client\llm\llm_constants.py',
  'core\client\llm\llm_client_pool.py',
  'core\client\llm\llm_processor.py',
  'core\client\llm\llm_minimax_search.py',
  'core\client\llm\llm_role_config.py',
  'core\client\llm\llm_get_selection.py',
  'core\client\llm\llm_handler.py',
  'core\client\llm\llm_message_builder.py',
  'core\client\llm\llm_role_formatter.py',
  'core\client\llm\llm_output_toast.py',
  'core\client\audio\system_audio_mute.py',
  'core\client\shortcut\task.py',
  'core\client\app.py',
  'core\ui\toast_manager.py',
  'core\ui\toast.py',
  'core\ui\toast_base.py',
  'core\ui\toast_text.py',
  'core\ui\toast_label.py'
)
foreach ($f in $files) {
  Copy-Item -LiteralPath (Join-Path $src $f) -Destination (Join-Path $dst $f) -Force
}
```

同步后重启客户端：

```powershell
$old = Get-Process -Name start_client -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq 'D:\AI\CapsWriter-Offline\start_client.exe' }
$old | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath 'D:\AI\CapsWriter-Offline\start_client.exe' -WorkingDirectory 'D:\AI\CapsWriter-Offline' -WindowStyle Hidden
```

如果改了服务端代码，再重启 `start_server.exe`。

## 不要提交的内容

不要提交这些内容：

- `D:\AI\CapsWriter-Offline\LLM\*.py` 里的个人 API key 版本。
- `.toast_state.json`
- `logs/`
- `models/`
- `internal/`
- `start_client.exe` / `start_server.exe`
- 任何包含 xAI、OpenAI/DeepSeek、GitHub token 前缀的文件。

提交前检查：

```powershell
git status --short
git diff --cached --name-only
git diff --cached --binary --no-ext-diff | Select-String -Pattern '(?:xai|sk)-[A-Za-z0-9]|[g]hp_|github[_]pat_|api_key\s*=\s*[''"][^''"]+'
```

## 常用验证

```powershell
python -m py_compile LLM\__init__.py core\client\llm\llm_role_config.py core\client\llm\llm_output_toast.py core\ui\toast_manager.py core\ui\toast.py core\ui\toast_base.py core\ui\toast_text.py core\ui\toast_label.py
git log --oneline --decorate -8
git status --short --branch
```
