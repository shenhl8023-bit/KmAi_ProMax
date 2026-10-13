# -*- coding: utf-8 -*-
import json
import os
import re


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
_CSS_DIR = os.path.join(_ASSETS_DIR, 'css')
_MODULES_DIR = os.path.join(_ASSETS_DIR, 'modules')

# CSS 按主题拆开,运行时按顺序拼成一个 <style> 块。
# 顺序很重要:`base` 必须先(定义变量),`responsive` 必须最后(媒体查询要覆盖默认布局)。
_CSS_FILES = (
    'base.css',          # :root 变量 + body 重置 + 顶栏 + 状态指示
    'chat.css',          # 聊天日志区 + 消息气泡 + tool-call
    'process_route.css', # 工艺路线 inbox 卡片 + 右侧滑出面板 + 时间线
    'workflow.css',      # 固定工作流 dock + 步骤胶囊 + pulse-ring 动画
    'similar_parts.css', # XML 相似零件查询 + STEP 双模型工作台
    'cards.css',         # 模板/自动识别/候选/保存状态卡片
    'xml_editor.css',    # XML 编辑器 + 流式输出 cursor 闪烁动画
    'bar.css',           # 底部输入栏
    'modals.css',        # 模型配置弹窗
    'responsive.css',    # 媒体查询(放最后,覆盖前面规则)
)


def _load(name, directory):
    with open(os.path.join(directory, name), encoding='utf-8') as f:
        return f.read()


# 在模块加载时把模板和资源一次性读入,运行时只做字符串拼接。
# 修改 assets/ 下的文件后需要重启服务才能生效。
_INDEX_HTML_TEMPLATE = _load('index.html', _ASSETS_DIR)
_STYLE_CSS = '\n\n'.join(_load(name, _CSS_DIR) for name in _CSS_FILES)

# 验证 modules 目录存在 + 入口文件存在,启动时就 fail-fast,
# 避免上线后才看到「入口找不到」的白屏。
_ENTRY_JS_PATH = os.path.join(_MODULES_DIR, 'entry.js')
if not os.path.isfile(_ENTRY_JS_PATH):
    raise RuntimeError(
        'frontend assets module entry not found: ' + _ENTRY_JS_PATH +
        ' —— 重构后 JS 拆到 assets/modules/,请确认 entry.js 存在'
    )

_LLM_STATUS_ENABLED = u"已启用 LLM 智能对话模式。"
_LLM_STATUS_DISABLED = (
    u"当前为关键词匹配模式，请在 config.ini 的 [LLM] 段配置 API Key 后重启。"
)

# 探测未替换占位符:匹配 {{任意非 } 字符}}
_PLACEHOLDER_RE = re.compile(r'\{\{[^}]+\}\}')


def build_index_html(llm_enabled, api_token=""):
    """组装并返回完整的聊天页面 HTML。

    模板里的占位符:
      {{style}}            —— assets/css/ 下 9 个 CSS 文件按顺序拼接的结果
      {{llm_status_json}}  —— 当前 LLM 启用状态的提示字符串,以 JS 字符串字面量注入
                              (作为 window.__LLM_STATUS__ 全局,在 entry.js 里读)

    JS 主体(原 {{app_js}})现在以 ES Module 形式拆到 assets/modules/,
    在模板里硬编码为 <script type="module" src="/assets/modules/entry.js">,
    运行时不再内联。静态文件路由见 backend/http_api.py。
    """
    llm_status_js = json.dumps(
        _LLM_STATUS_ENABLED if llm_enabled else _LLM_STATUS_DISABLED,
        ensure_ascii=False,
    )
    api_token_script = (
        '<script>window.__KMAI_API_TOKEN__ = %s;</script>' %
        json.dumps(api_token or "", ensure_ascii=False)
    )

    html = (
        _INDEX_HTML_TEMPLATE
        .replace('{{style}}', _STYLE_CSS)
        .replace('{{llm_status_json}}', llm_status_js)
    )
    # API token 由本次服务进程生成,只注入当前页面,避免任意网页跨域调用本地高权限接口。
    html = html.replace(
        '<script>window.__LLM_STATUS__ = ',
        api_token_script + '\n  <script>window.__LLM_STATUS__ = ',
        1,
    )

    # 防御性检查:任何 {{...}} 残留都说明模板或资源里有未处理的占位符,
    # 直接抛错,避免上线后才看到花括号字面量。
    leftover = sorted(set(_PLACEHOLDER_RE.findall(html)))
    if leftover:
        raise RuntimeError(
            'build_index_html: unresolved placeholders: ' + ', '.join(leftover)
        )

    return html
