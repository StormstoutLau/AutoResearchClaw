/**
 * REST API client for ResearchClaw.
 */
const API = {
  base: '/api',

  async get(path) {
    const res = await fetch(`${this.base}${path}`);
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  async post(path, body = {}) {
    const res = await fetch(`${this.base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  // Convenience methods
  health() { return this.get('/health'); },
  config() { return this.get('/config'); },
  pipelineStatus() { return this.get('/pipeline/status'); },
  pipelineStages() { return this.get('/pipeline/stages'); },
  startPipeline(opts) { return this.post('/pipeline/start', opts); },
  stopPipeline() { return this.post('/pipeline/stop'); },
  listRuns() { return this.get('/runs'); },
  getRun(id) { return this.get(`/runs/${id}`); },
  getMetrics(id) { return this.get(`/runs/${id}/metrics`); },
  listProjects() { return this.get('/projects'); },

  /**
   * One page of the run event log (A1-2).
   * @param {string} id run id
   * @param {number|null} after cursor; server also honors Last-Event-ID
   */
  listEvents(id, after = null, limit = null) {
    const q = new URLSearchParams();
    if (after !== null) q.set('after', after);
    if (limit !== null) q.set('limit', limit);
    const qs = q.toString();
    return this.get(`/runs/${id}/events${qs ? `?${qs}` : ''}`);
  },

  /**
   * Subscribe to the SSE stream. Browser EventSource reconnects automatically
   * and replays with Last-Event-ID; a stream.gap event means the cursor fell
   * outside the retained window and the UI should refetch from oldest_seq.
   */
  streamEvents(id, { after = null, onEvent, onGap, onClose, onError } = {}) {
    const q = after === null ? '' : `?after=${encodeURIComponent(after)}`;
    const es = new EventSource(`${this.base}/runs/${id}/events/stream${q}`);
    const closed = { value: false };
    const finish = () => {
      if (closed.value) return;
      closed.value = true;
      try { es.close(); } catch (e) { /* ignore */ }
      if (onClose) onClose();
    };
    es.addEventListener('stream.gap', (e) => {
      try { if (onGap) onGap(JSON.parse(e.data)); } catch (err) { /* ignore */ }
    });
    EVENT_TYPES.forEach((type) => {
      es.addEventListener(type, (e) => {
        let payload = null;
        try { payload = JSON.parse(e.data); } catch (err) { /* ignore */ }
        if (onEvent) onEvent(payload);
        if (TERMINAL_EVENTS.indexOf(type) !== -1) finish();
      });
    });
    es.onerror = (e) => {
      // EventSource retries by itself; surface the error but keep the stream
      // open unless the run already terminated.
      if (onError) onError(e);
      if (closed.value) finish();
    };
    es.closeRun = finish;
    return es;
  },
};

// Mirrors researchclaw/runtime/event_log.EVENT_TYPES and TERMINAL_EVENTS.
const EVENT_TYPES = [
  'run.started', 'run.completed', 'run.failed', 'run.paused',
  'stage.started', 'stage.completed', 'stage.failed', 'stage.retried',
  'tool.call', 'tool.result', 'llm.call', 'llm.result',
  'approval.required', 'effect.queued', 'effect.done',
  'event_log_truncated', 'event_log_rolled',
];
const TERMINAL_EVENTS = ['run.completed', 'run.failed', 'run.paused'];
