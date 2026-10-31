const API_BASE = '/api'

export type User = {
  id: number
  email: string
  created_at: string
}

type TokenResponse = {
  access_token: string
  token_type: string
}

/** An error returned by the backend, with its HTTP status code. */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Turn FastAPI's error body into a readable message. */
function errorMessage(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    // Validation errors (422) come as a list of problems
    if (Array.isArray(detail) && detail.length > 0) {
      return String(detail[0]?.msg ?? 'Invalid input')
    }
  }
  return 'Something went wrong'
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(body))
  }
  return body as T
}

export function signup(email: string, password: string): Promise<User> {
  return request<User>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function fetchMe(token: string): Promise<User> {
  return request<User>('/auth/me', {}, token)
}
