// model_config.js —— 顶栏「模型配置」弹窗。
//
// 整个前端的设置入口唯一一处。点保存后调 /api/config/llm,后端会
// 立即重载 LLM client(见 backend/agent_config._save_llm_config),
// 然后由 chat.js 重新 ping() 刷新顶栏状态。

import {
  dom, escapeHtml, setStatus, addBotMsg,
  requestJson, ping,
} from './shared.js';

/** 弹出模型配置对话框。读当前配置填表,提交后写回并刷新。 */
export function openModelConfig() {
  const old = document.querySelector('.config-backdrop');
  if (old) old.remove();
  const backdrop = document.createElement('div');
  backdrop.className = 'config-backdrop';
  backdrop.innerHTML =
    '<div class="config-dialog" role="dialog" aria-modal="true">' +
      '<div class="config-dialog-head">' +
        '<div class="config-dialog-title">模型配置</div>' +
        '<button class="config-dialog-close" type="button" title="关闭">&times;</button>' +
      '</div>' +
      '<form class="config-dialog-body" id="llmConfigForm">' +
        '<div class="config-row"><label>Provider</label><input name="provider" placeholder="openai / deepseek / local" autocomplete="off"></div>' +
        '<div class="config-row"><label>Base URL</label><input name="base_url" placeholder="https://api.openai.com/v1" autocomplete="off"></div>' +
        '<div class="config-row"><label>Model</label><input name="model" placeholder="gpt-4o / deepseek-chat" autocomplete="off"></div>' +
        '<div class="config-row"><label>API Key</label><input name="api_key" type="password" placeholder="留空表示保留当前 Key" autocomplete="new-password"></div>' +
        '<div class="config-row inline">' +
          '<label>Max Tokens</label><input name="max_tokens" type="number" min="1" step="1">' +
          '<label>Temperature</label><input name="temperature" type="number" min="0" max="2" step="0.1">' +
        '</div>' +
        '<label class="config-hint"><input name="clear_api_key" type="checkbox"> 清空当前 API Key(勾选后忽略上方 API Key 输入)</label>' +
        '<div class="config-hint" id="llmConfigHint">正在读取当前配置...</div>' +
        '<div class="config-status" id="llmConfigStatus"></div>' +
      '</form>' +
      '<div class="config-actions">' +
        '<button class="config-cancel" type="button">取消</button>' +
        '<button class="config-save" type="submit" form="llmConfigForm">保存并生效</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);

  const form = backdrop.querySelector('#llmConfigForm');
  const saveBtn = backdrop.querySelector('.config-save');
  const status = backdrop.querySelector('#llmConfigStatus');
  const hint = backdrop.querySelector('#llmConfigHint');
  const close = function() { backdrop.remove(); dom.input.focus(); };
  backdrop.querySelector('.config-dialog-close').addEventListener('click', close);
  backdrop.querySelector('.config-cancel').addEventListener('click', close);
  backdrop.addEventListener('click', function(ev) { if (ev.target === backdrop) close(); });

  function setConfigStatus(kind, text) {
    status.className = 'config-status ' + (kind || '');
    status.textContent = text || '';
  }
  function fillForm(cfg) {
    form.provider.value = cfg.provider || '';
    form.base_url.value = cfg.base_url || '';
    form.model.value = cfg.model || '';
    form.max_tokens.value = cfg.max_tokens || 4096;
    form.temperature.value = cfg.temperature !== undefined ? cfg.temperature : 0.3;
    form.api_key.value = '';
    form.api_key.placeholder = cfg.api_key_set ? ('已设置: ' + (cfg.api_key_masked || '******') + '，留空保留') : '未设置，请输入 API Key';
    hint.textContent = '当前配置文件: ' + (cfg.config_path || 'config.ini');
  }

  requestJson('GET', '/api/config/llm', null, function(data) {
    fillForm((data && data.config) || {});
    setConfigStatus('ok', '已读取当前模型配置');
  }, function(err) {
    setConfigStatus('err', '读取失败: ' + err.message);
  }, 15000);

  form.addEventListener('submit', function(ev) {
    ev.preventDefault();
    const payload = {
      provider: form.provider.value.trim(),
      base_url: form.base_url.value.trim(),
      model: form.model.value.trim(),
      api_key: form.api_key.value.trim(),
      max_tokens: Number(form.max_tokens.value || 4096),
      temperature: Number(form.temperature.value || 0.3),
      clear_api_key: !!form.clear_api_key.checked
    };
    saveBtn.disabled = true;
    setConfigStatus('', '正在保存配置...');
    requestJson('POST', '/api/config/llm', JSON.stringify(payload), function(data) {
      const cfg = (data && data.config) || {};
      fillForm(cfg);
      form.clear_api_key.checked = false;
      saveBtn.disabled = false;
      setConfigStatus('ok', '已保存，新模型配置已生效(会话历史已重置)');
      addBotMsg('✅ 模型配置已更新：' + escapeHtml(cfg.model || '') + '<br><span style="color:#64748b;font-size:12px">Base URL: ' + escapeHtml(cfg.base_url || '') + '</span>');
      ping();
    }, function(err) {
      saveBtn.disabled = false;
      setConfigStatus('err', '保存失败: ' + err.message);
    }, 30000);
  });
}
