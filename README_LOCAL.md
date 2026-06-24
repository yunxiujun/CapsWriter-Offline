# CapsWriter-Offline 本地维护说明

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
- Toast 支持 `toast_position_y` 初始屏幕 y 坐标。
- Toast 右侧按钮：
  - `固`：固定当前窗口位置。
  - `移`：取消固定，允许移动。
  - `消/留`：切换自动消失或保留到 `ESC`。
- `固/移` 和 `消/留` 会保存到运行目录的 `.toast_state.json`，重启后仍保留。
- `.toast_state.json` 已加入 `.gitignore`，不会提交。

## 角色文件里的本地配置

所有运行目录的 `D:\AI\CapsWriter-Offline\LLM\*.py` 都只保留这类注释配置：

```python
# toast_position_y = 420                 # 可选：Toast 窗口初始屏幕高度/y 坐标（-1 表示屏幕中间）
```

需要某个角色固定初始高度位置时，只删除这一行前面的 `#`。

固定/移动、自动消失/保留不要再写进 `LLM\*.py`，在 Toast 浮动窗口右侧按钮里设置即可。

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
core/client/llm/llm_role_config.py
core/client/llm/llm_output_toast.py
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
  'core\client\llm\llm_role_config.py',
  'core\client\llm\llm_output_toast.py',
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
