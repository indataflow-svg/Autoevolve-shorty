export type FieldIssue = { field: string; message: string }

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public method: string,
    public path: string,
    public issues: FieldIssue[] = [],
    public retryAfterSeconds: number | null = null,
    public requestId: string | null = null,
  ) { super(message) }
}

export type Credentials = { username: string; password: string }

function basic(credentials: Credentials): string {
  const bytes = new TextEncoder().encode(`${credentials.username}:${credentials.password}`)
  return `Basic ${btoa(String.fromCharCode(...bytes))}`
}

function fieldIssues(detail: unknown): FieldIssue[] {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return Object.entries(detail).filter((entry): entry is [string, string] => typeof entry[1] === 'string').map(([field, message]) => ({ field, message }))
  }
  if (!Array.isArray(detail)) return []
  return detail.flatMap(item => {
    if (!item || typeof item !== 'object') return []
    const issue = item as { loc?: unknown; msg?: unknown }
    if (typeof issue.msg !== 'string') return []
    const field = Array.isArray(issue.loc) ? issue.loc.filter(part => part !== 'body').join('.') : 'request'
    return [{ field: field || 'request', message: issue.msg }]
  })
}

function responseMessage(status: number, detail: unknown, statusText: string, issues: FieldIssue[], retryAfter: number | null) {
  const backend = typeof detail === 'string' ? detail : ''
  if (status === 401) return 'Authentication failed. Sign in again.'
  if (status === 403) return `You are authenticated, but this action is not authorized.${backend ? ` ${backend}` : ''}`
  if (status === 404) return backend && backend !== 'Not Found' ? backend : 'This API route does not exist.'
  if (status === 422) return issues.length ? issues.map(issue => `${issue.field}: ${issue.message}`).join('; ') : backend || 'The request did not match the backend contract.'
  if (status === 429) return `Rate limited.${retryAfter !== null ? ` Try again in ${retryAfter} seconds.` : ' Try again later.'}`
  if (status >= 500) return `Server or provider failure.${backend ? ` ${backend}` : ''}`
  return backend || statusText || `Request failed (${status})`
}

async function request(
  path: string, credentials: Credentials, options: RequestInit = {}, actionToken?: string,
): Promise<Response> {
  const headers = new Headers(options.headers)
  headers.set('Authorization', basic(credentials))
  headers.set('X-Requested-With', 'XMLHttpRequest')
  if (actionToken) headers.set('X-Founder-Action-Token', actionToken)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(path, { ...options, headers, cache: 'no-store' })
  } catch {
    throw new ApiError(0, 'Could not reach AutoEvolve. Check the server connection.', (options.method || 'GET').toUpperCase(), path)
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : null
    const issues = fieldIssues(detail)
    const retryHeader = response.headers?.get('Retry-After')
    const parsedRetry = retryHeader ? /^\d+$/.test(retryHeader)
      ? Number(retryHeader)
      : Number.isNaN(Date.parse(retryHeader)) ? null : Math.max(0, Math.ceil((Date.parse(retryHeader) - Date.now()) / 1000))
      : null
    const requestId = response.headers?.get('X-Request-ID') || response.headers?.get('X-Correlation-ID') || null
    if (response.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('autoevolve:auth-failed'))
    throw new ApiError(
      response.status,
      responseMessage(response.status, detail, response.statusText, issues, parsedRetry),
      (options.method || 'GET').toUpperCase(), path, issues, parsedRetry, requestId,
    )
  }
  return response
}

export async function api<T>(path: string, credentials: Credentials, options: RequestInit = {}, actionToken?: string): Promise<T> {
  return (await request(path, credentials, options, actionToken)).json() as Promise<T>
}

export async function apiBlob(path: string, credentials: Credentials): Promise<Blob> {
  return (await request(path, credentials)).blob()
}
