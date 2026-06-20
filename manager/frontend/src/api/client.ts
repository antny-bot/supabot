export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function readErrorBody(res: Response) {
  const contentType = res.headers.get('content-type') ?? ''

  if (contentType.includes('application/json')) {
    return res.json().catch(() => ({}))
  }

  const text = await res.text().catch(() => '')
  return text ? { error: text } : {}
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers ?? {})

  if (options?.body !== undefined && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(path, {
    credentials: 'include',
    headers,
    ...options,
  })
  if (res.status === 401) {
    window.location.href = '/login'
    throw new ApiError('Unauthorized', res.status, {})
  }
  if (!res.ok) {
    const body = await readErrorBody(res) as { error?: string }
    throw new ApiError(body.error ?? `HTTP ${res.status}`, res.status, body)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  postForm: <T>(path: string, body: FormData) =>
    request<T>(path, {
      method: 'POST',
      body,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
