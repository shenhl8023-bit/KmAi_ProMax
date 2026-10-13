const WORKFLOW_STEP_IDS = [
  'select_group_template',
  'auto_identify_template',
  'feature_reasoning',
  'ai_process_input',
  'generate_all_model',
];

function createInitialState() {
  return {
    runId: '',
    status: 'idle',
    mode: '',
    activeStepId: WORKFLOW_STEP_IDS[0],
    runningStepId: '',
    awaitingStepId: '',
    runningAll: false,
    waitingUserStepId: '',
    autoSubmittedRoute: false,
    doneStepIds: {},
    continueFromStepId: '',
    error: null,
  };
}

function cloneState(state) {
  return {
    ...state,
    doneStepIds: { ...state.doneStepIds },
    error: state.error ? { ...state.error } : null,
  };
}

function createRunId(sequence) {
  return 'workflow-' + sequence + '-' + Date.now().toString(36);
}

export function createWorkflowCoordinator(options = {}) {
  const onCancel = typeof options.onCancel === 'function' ? options.onCancel : null;
  let sequence = 0;
  let state = createInitialState();
  let cancelHandle = null;

  function isActive() {
    return state.status === 'running' || state.status === 'awaiting';
  }

  function getState() {
    return cloneState(state);
  }

  function isCurrentRun(runId) {
    return Boolean(runId) && runId === state.runId;
  }

  function cancelCurrentRun() {
    if (cancelHandle && typeof cancelHandle.abort === 'function') {
      cancelHandle.abort();
    }
    if (onCancel && state.runId) onCancel(state.runId);
    cancelHandle = null;
  }

  function beginRun(mode, startStepId) {
    if (isActive()) return { accepted: false, runId: state.runId, state: getState() };
    cancelCurrentRun();
    sequence += 1;
    const runId = createRunId(sequence);
    state = {
      ...createInitialState(),
      runId,
      status: 'running',
      mode: mode || 'single',
      activeStepId: startStepId || WORKFLOW_STEP_IDS[0],
      runningAll: mode === 'all',
    };
    cancelHandle = typeof AbortController === 'function' ? new AbortController() : null;
    return { accepted: true, runId, signal: cancelHandle ? cancelHandle.signal : null, state: getState() };
  }

  function canMutate(runId) {
    return isCurrentRun(runId) && state.status !== 'failed' && state.status !== 'cancelled' && state.status !== 'completed';
  }

  function startStep(runId, stepId) {
    if (!canMutate(runId)) return false;
    state = { ...state, status: 'running', activeStepId: stepId, runningStepId: stepId, awaitingStepId: '', waitingUserStepId: '', error: null };
    return true;
  }

  function awaitStep(runId, stepId) {
    if (!canMutate(runId)) return false;
    state = { ...state, status: 'awaiting', activeStepId: stepId, runningStepId: '', awaitingStepId: stepId, waitingUserStepId: stepId, error: null };
    return true;
  }

  function completeStep(runId, stepId) {
    if (!canMutate(runId)) return false;
    const doneStepIds = { ...state.doneStepIds, [stepId]: true };
    const index = WORKFLOW_STEP_IDS.indexOf(stepId);
    const nextStepId = WORKFLOW_STEP_IDS[index + 1] || stepId;
    const completedAll = index === WORKFLOW_STEP_IDS.length - 1 || Object.keys(doneStepIds).length === WORKFLOW_STEP_IDS.length;
    state = {
      ...state,
      status: completedAll ? 'completed' : 'idle',
      activeStepId: nextStepId,
      runningStepId: '',
      awaitingStepId: '',
      waitingUserStepId: '',
      runningAll: completedAll ? false : state.runningAll,
      doneStepIds,
      continueFromStepId: state.continueFromStepId === stepId ? '' : state.continueFromStepId,
    };
    if (completedAll) cancelCurrentRun();
    return true;
  }

  function failRun(runId, error) {
    if (!isCurrentRun(runId) || !isActive()) return false;
    state = { ...state, status: 'failed', runningStepId: '', awaitingStepId: '', waitingUserStepId: '', runningAll: false, error: error || { message: 'workflow failed' } };
    cancelCurrentRun();
    return true;
  }

  function resetRun() {
    cancelCurrentRun();
    state = createInitialState();
    return getState();
  }

  function getSignal(runId) {
    return isCurrentRun(runId) && cancelHandle ? cancelHandle.signal : null;
  }

  function setIdle(runId, stepId) {
    if (!isCurrentRun(runId)) return false;
    state = { ...state, status: 'idle', activeStepId: stepId || state.activeStepId, runningStepId: '', awaitingStepId: '', waitingUserStepId: '', runningAll: false };
    return true;
  }

  function prepareRetry(runId, stepId, doneStepIds) {
    if (!isCurrentRun(runId)) return false;
    state = { ...state, status: 'idle', activeStepId: stepId, runningStepId: '', awaitingStepId: '', waitingUserStepId: '', runningAll: false, doneStepIds: { ...(doneStepIds || {}) }, continueFromStepId: stepId, error: null };
    return true;
  }

  function patchState(runId, patch) {
    if (!isCurrentRun(runId)) return false;
    state = { ...state, ...(patch || {}), doneStepIds: patch && patch.doneStepIds ? { ...patch.doneStepIds } : state.doneStepIds };
    return true;
  }

  return { beginRun, startStep, awaitStep, completeStep, failRun, resetRun, isCurrentRun, getSignal, getState, setIdle, prepareRetry, patchState };
}

export { WORKFLOW_STEP_IDS, createInitialState };

