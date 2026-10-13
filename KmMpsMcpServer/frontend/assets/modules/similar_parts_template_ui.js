export function recommendedTemplateRowMarkup() {
  return '<div class="similar-parts-tmpl-row">' +
    '<div class="sp-tmpl-label">' +
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>' +
      '<span>推荐模板</span>' +
    '</div>' +
    '<strong data-role="template-name">—</strong>' +
    '<span class="similar-parts-template-edited" data-role="template-edited" hidden>已编辑</span>' +
    '<button type="button" class="similar-parts-template-edit" data-role="edit-template" title="编辑当前映射的分组模板">编辑</button>' +
  '</div>';
}

export function recommendedTemplateLabel(candidate, edited) {
  return String((edited && edited.filename) || (candidate && candidate.template && candidate.template.name) || '—');
}

export function buildTemplateApplyPayload(uploadId, candidate, edited) {
  const payload = { uploadId, candidateId: candidate && candidate.candidateId };
  if (edited && edited.filename && edited.xml) payload.editedTemplate = edited;
  return payload;
}
