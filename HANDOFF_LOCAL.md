# Handoff: CapsWriter-Offline 本地 fork

## 目标

维护用户自己的 CapsWriter-Offline 改造版，同时后续可以继续合并官方 `HaujetZhao/CapsWriter-Offline` 的更新。

## 当前仓库状态

- 维护目录：`D:\AI\CapsWriter-Offline-git`
- 运行目录：`D:\AI\CapsWriter-Offline`
- 当前维护分支：`my-local-adapt`
- 用户 fork：`https://github.com/yunxiujun/CapsWriter-Offline.git`
- 官方上游：`https://github.com/HaujetZhao/CapsWriter-Offline.git`
- 官方默认分支：`master`
- `upstream` push URL 已设为 `DISABLED`
- 运行目录已于 2026-08-01 同步官方 `upstream/master` 提交 `7d7fac3`。
- 同步采用本地优先策略：`core/tools/chinese_itn/replacer.py` 保留本地 ITN 规则，
  `hot.txt` 和 `hot-rule.txt` 只增量加入黑名单说明与 `A.S.R -> ASR` 规则。
- 升级前备份：`D:\AI\CapsWriter-Offline-backups\official-merge-20260801-144847`。

最新本地功能提交：

```text
4bc12e0 Persist Toast window button state
69666d9 Split Toast position lock and auto dismiss
aa47cce Highlight Toast pin state
39af546 Add Toast pin controls
7e3814c Add Toast fixed position options
3e166a3 Add xAI Responses API support
fab441c Preserve bare large-unit phrases in ITN
```

## 已完成的功能

1. xAI/Grok 接入
   - 在 OpenAI 兼容客户端里识别 xAI 地址并使用 xAI 超时配置。
   - 支持 `use_responses_api` 分支。
   - 支持 xAI `web_search` 工具。

2. MiniMax Token Plan 联网搜索
   - 使用大陆区 `https://api.minimaxi.com/v1/coding_plan/search` 获取实时结果。
   - `extra_options['minimax_web_search'] = True` 时启用，两段式调用 MiniMax 搜索和模型。
   - 搜索控制参数不会传给 Chat Completions；失败时直接报错，避免假联网。
   - 运行目录 `LLM\联网助理.py` 使用 `MiniMax-M3`，API Key 留空，由用户自行填写。

3. Toast 配置和交互
   - `LLM\*.py` 只保留 `toast_position_y` 作为可选初始 y 坐标。
   - 运行目录所有角色文件已加入注释示例：

```python
# toast_position_y = 420                 # 可选：Toast 窗口初始屏幕高度/y 坐标（-1 表示屏幕中间）
```

   - Toast 右侧有 `固`、`移`、`消/留` 按钮。
   - `固/移` 和 `消/留` 的选择保存在运行目录 `.toast_state.json`。
   - `.toast_state.json` 不提交。

4. LLM 选区与剪贴板上下文
   - 浏览器整页选区不再只固定等待 0.1 秒；现在用唯一剪贴板标记并轮询等待。
   - 修复选中文字与原剪贴板内容相同时被误判为无选区。
   - 非默认角色唤醒后，语音包含 `剪贴板/剪切板/剪贴版/剪切版` 时，
     直接读取当前剪贴板文字，优先于模拟 `Ctrl+C` 的选区读取。
   - 运行目录所有角色都保留可调整的注释配置，默认上限为 20000 字符。

5. 录音期间静音系统输出
   - `config_client.py` 中的 `mute_system_audio_while_recording` 是总开关。
   - 按下识别快捷键后先保存 Windows 默认输出设备静音状态，再临时静音。
   - 完成、取消、异常和客户端正常退出都会恢复录音前状态。
   - 使用共享计数，两个录音入口重叠时不会提前恢复声音。
   - 依赖 `pycaw==20251023` 和 `comtypes==1.4.16`。

6. 官方 v2.6 后续修复已同步到运行目录
   - 麦克风权限失败和模型目录错放会给出友好提示。
   - 热词检索使用批量 FastRAG，支持黑名单与 Unicode 字母音素。
   - 支持正负数、斤两、省略尾随单位及英文缩写去点。
   - 回归验证：59 个实际热词加载成功，100 次检索约 36 ms；ITN、黑名单、
     Unicode 热词、Qwen3-ASR 启动和 WebSocket 连接均通过。

## 重要边界

- 维护目录是干净 Git 工作目录。
- 运行目录包含个人配置、模型、日志、exe 和 API key。
- 不要从运行目录直接 `git add .`。
- 不要提交 `LLM\联网助理.py`、`LLM\马斯克助理.py` 等包含 API key 的本地角色文件。
- 通用模板 `LLM\__init__.py` 可以提交。

## 官方更新合流流程

在维护目录执行：

```powershell
cd D:\AI\CapsWriter-Offline-git
git checkout my-local-adapt
git fetch upstream master
git merge upstream/master
```

无冲突时：

```powershell
python -m py_compile LLM\__init__.py core\client\llm\llm_role_config.py core\client\llm\llm_output_toast.py core\ui\toast_manager.py core\ui\toast.py core\ui\toast_base.py core\ui\toast_text.py core\ui\toast_label.py
git push
```

有冲突时：

```powershell
git status
rg "<<<<<<<|=======|>>>>>>>" .
```

解决冲突后：

```powershell
git add <resolved-files>
git commit
python -m py_compile LLM\__init__.py core\client\llm\llm_role_config.py core\client\llm\llm_output_toast.py core\ui\toast_manager.py core\ui\toast.py core\ui\toast_base.py core\ui\toast_text.py core\ui\toast_label.py
git push
```

## 合流后同步运行目录

只同步通用源码：

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

然后重启客户端：

```powershell
$old = Get-Process -Name start_client -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq 'D:\AI\CapsWriter-Offline\start_client.exe' }
$old | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath 'D:\AI\CapsWriter-Offline\start_client.exe' -WorkingDirectory 'D:\AI\CapsWriter-Offline' -WindowStyle Hidden
```

## 提交前检查

```powershell
git status --short --branch
git diff --cached --name-only
git diff --cached --binary --no-ext-diff | Select-String -Pattern '(?:xai|sk)-[A-Za-z0-9]|[g]hp_|github[_]pat_|api_key\s*=\s*[''"][^''"]+'
```

如果输出疑似密钥，立刻取消提交并检查 staged 文件：

```powershell
git restore --staged <file>
```

## 当前运行目录说明

- 运行目录客户端已多次重启验证。
- `.toast_state.json` 只有用户点击 Toast 右侧按钮后才会出现。
- 默认没有状态文件时，Toast 是可移动且自动消失。
- 用户希望所有角色文件中的 `toast_position_y = 420` 默认注释，按需自己删 `#` 启用。
