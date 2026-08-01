"""知识库助理角色模板。API Key 请只填写在本地运行目录。"""

# ==================== 基本信息 ====================
name = '知识库助理 | 资料助理'
enabled = True

# ==================== API 配置 ====================
provider = 'deepseek'
api_url = ''
api_key = ''
model = 'deepseek-v4-flash'

# ==================== 上下文管理 ====================
max_context_length = 1024 * 1024

# ==================== 功能配置 ====================
enable_hotwords = False
enable_thinking = False
enable_history = True
enable_read_selection = True
selection_max_length = 20000
# selection_copy_timeout = 0.8
# enable_read_clipboard = True
# clipboard_keywords = ('剪贴板', '剪切板', '剪贴版', '剪切版')
# clipboard_max_length = 20000
enable_knowledge_base = True            # 此角色默认启用知识库
# knowledge_base_folder = ''            # 留空使用 LLM知识库/知识库助理
# knowledge_base_top_k = 8
# knowledge_base_max_chars = 50000
# knowledge_base_evidence_max_chars = 12000
# knowledge_base_evidence_top_k = 3

# ==================== 输出配置 ====================
output_mode = 'toast'

# ==================== Toast 弹窗配置 ====================
toast_initial_width = 0.5
toast_initial_height = 0
toast_font_family = '楷体'
toast_font_size = 23
toast_font_color = 'white'
toast_bg_color = '#075077'
toast_duration = 3000
toast_editable = True

# ==================== 生成参数 ====================
temperature = 0.3
top_p = 0.9
max_tokens = 4096
stop = ''

# ==================== 高级选项 ====================
extra_options = {}

# ==================== 提示词前缀 ====================
prompt_prefix_hotwords = '热词列表：'
prompt_prefix_selection = '选中文字：'
# prompt_prefix_clipboard = '剪贴板内容：'
prompt_prefix_knowledge_base = '本地知识库资料：'
prompt_prefix_input = '用户问题：'

# ==================== System Prompt ====================
system_prompt = '''
你是一个严谨的本地知识库助理。

工作规则：
- 仅根据当前请求中提供的“本地知识库资料”回答问题。
- 不得使用模型自身知识、常识或猜测补充资料中没有的信息。
- 优先给出直接、清楚的答案，并尽量注明来源文件名。
- 多份资料存在冲突时，分别列出冲突内容及其来源，不自行判断真伪。
- 资料不足时只回答“知识库中没有找到相关信息”，并说明缺少哪方面资料。
- 你的回答后会由程序自动附加未经模型修改的相关原文，不需要你重复抄写原文。
'''
