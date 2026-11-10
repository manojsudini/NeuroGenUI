// Thin client for the NeuroGenUI REST API (docs/contract.md §4). Same-origin URLs only.

export class ApiError extends Error {
  constructor(status, detail, path) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
    this.path = path
  }
  get offline() {
    return this.status === 0 || this.status === 502 || this.status === 504
  }
  get noKey() {
    return this.status === 503
  }
}

/** Human-friendly message for any error thrown by this module. */
export function errMessage(e) {
  if (!(e instanceof ApiError)) return e?.message || 'Something went wrong'
  if (e.offline) return 'The NeuroGenUI API is not reachable on port 8200. Start the backend with run.bat (or uvicorn app.main:app --port 8200).'
  if (e.noKey) return /OPENAI/i.test(e.message) ? 'The OpenAI API key is not configured on the server. Add OPENAI_API_KEY to project/.env and restart the backend. OpenCV-only sketch analysis (mode "cv") still works.' : e.message
  if (Array.isArray(e.detail)) return e.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  return e.message || `Request failed (${e.status})`
}

async function parse(res, path) {
  const type = res.headers.get('content-type') || ''
  let body = null
  try {
    body = type.includes('json') ? await res.json() : await res.text()
  } catch {
    body = null
  }
  if (!res.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : body || res.statusText
    // Vite's proxy answers 500 with an empty body / ECONNREFUSED text when the backend is down.
    const down = res.status === 500 && (!body || (typeof body === 'string' && /ECONNREFUSED|proxy/i.test(body)))
    throw new ApiError(down ? 0 : res.status, detail, path)
  }
  return body
}

async function req(method, path, body, opts = {}) {
  const init = { method, headers: {}, signal: opts.signal }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(path, init)
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'Network error', path)
  }
  return parse(res, path)
}

/**
 * POST with ?stream=1 and read the text/event-stream body (fetch + ReadableStream).
 * Calls onEvent for every JSON event. Resolves with the final Version.
 * Falls back gracefully if the server answers with plain JSON.
 */
async function stream(path, body, onEvent, signal) {
  let res
  try {
    res = await fetch(`${path}?stream=1`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify(body), signal })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'Network error', path)
  }
  const type = res.headers.get('content-type') || ''
  if (!res.ok || !type.includes('event-stream')) {
    const v = await parse(res, path)
    return v?.version || v
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let result = null
  let failure = null
  const handle = (block) => {
    const data = block
      .split('\n')
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.slice(5).trimStart())
      .join('\n')
    if (!data) return
    let ev
    try {
      ev = JSON.parse(data)
    } catch {
      return
    }
    const evName = block.match(/^event:\s*(.+)$/m)?.[1]?.trim()
    if (!ev.event && evName) ev.event = evName
    onEvent?.(ev)
    if (ev.event === 'result') result = ev.version || ev.data?.version || ev
    if (ev.event === 'error') failure = new ApiError(ev.status || 500, ev.detail || 'Pipeline failed', path)
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      handle(buf.slice(0, i))
      buf = buf.slice(i + 2)
    }
  }
  if (buf.trim()) handle(buf)
  if (failure) throw failure
  if (!result) throw new ApiError(500, 'The stream ended without a result', path)
  return result
}

const enc = encodeURIComponent

export const api = {
  health: () => req('GET', '/api/health'),
  projects: () => req('GET', '/api/projects'),
  createProject: (name) => req('POST', '/api/projects', { name }),
  deleteProject: (id) => req('DELETE', `/api/projects/${enc(id)}`),
  project: (id) => req('GET', `/api/project/${enc(id)}`),
  uploadSketch: (blob, projectId, filename = 'sketch.png') => {
    const f = new FormData()
    f.append('file', blob, filename)
    if (projectId) f.append('project_id', projectId)
    return req('POST', '/api/upload-sketch', f)
  },
  analyze: (sketchId, mode = 'hybrid') => req('POST', '/api/analyze-sketch', { sketch_id: sketchId, mode }),
  voiceToText: (blob) => {
    const f = new FormData()
    const ext = blob.type.includes('ogg') ? 'ogg' : blob.type.includes('mp4') ? 'm4a' : blob.type.includes('wav') ? 'wav' : 'webm'
    f.append('file', blob, `voice.${ext}`)
    return req('POST', '/api/voice-to-text', f)
  },
  interpret: (text, projectId) => req('POST', '/api/interpret', { text, project_id: projectId }),
  generate: (body, onEvent, signal) => stream('/api/generate-ui', body, onEvent, signal),
  modify: (body, onEvent, signal) => stream('/api/modify-ui', body, onEvent, signal),
  validate: (projectId, version, repair = false) => req('POST', '/api/validate-ui', { project_id: projectId, version, repair }),
  versions: (id) => req('GET', `/api/projects/${enc(id)}/versions`),
  version: (id, n) => req('GET', `/api/projects/${enc(id)}/versions/${n}`),
  restore: (id, n) => req('POST', `/api/projects/${enc(id)}/versions/${n}/restore`),
  patchIr: (id, ir, baseVersion) => req('PATCH', `/api/projects/${enc(id)}/ir`, { ir, base_version: baseVersion }),
  putCode: (id, files, preview, baseVersion) => req('PUT', `/api/projects/${enc(id)}/code`, { files, preview, base_version: baseVersion }),
  exportUrl: (id, n) => `/api/projects/${enc(id)}/versions/${n}/export.zip`,
  previewUrl: (id, n) => `/runtime/preview.html?project=${enc(id)}${n != null ? `&version=${n}` : ''}`,
  samples: () => req('GET', '/api/samples'),
  dataset: () => req('GET', '/api/dataset'),
  evaluation: () => req('GET', '/api/eval'),
  json: (url) => req('GET', url),
}
