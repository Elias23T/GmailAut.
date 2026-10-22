export interface User { id: string; name: string; email: string | null; username: string | null; status: string; is_platform_admin: boolean }
export interface AuthResult { user: User; access_token: string; expires_in: number }
export interface Tenant { id: string; name: string; slug: string; membership_id: string; status: 'active' | 'disabled' | 'suspended'; created_at: string }
export interface Mailbox { id: string; tenant_id: string; email: string; display_name: string; imap_host: string; imap_port: number; status: string; can_read: boolean }
export interface Grant { id: string; membership_id: string; mailbox_id: string }
export interface Client { id: string; membership_id: string; name: string; email: string; status: string }
export interface ConnectionSettings { mcp_url: string; public_https: boolean; authentication: string; scope: string; redirect_uris: string[] }
export interface Connection { id: string; membership_id: string; name: string; email: string; active: boolean; created_at: string; expires_at: string }
export interface AuditEvent { id: string; actor_user_id: string | null; mailbox_id: string | null; action: string; outcome: string; created_at: string; request_id: string }
export interface MessageSummary { uid: number; subject: string; sender: string; date: string; size: number; seen: boolean }
export interface MessagePage { uid_validity: number; total: number; items: MessageSummary[] }
export interface MessageDetail extends MessageSummary { recipients: string; body: string; attachments: string[]; truncated: boolean }

let accessToken: string | null = null
export function setAccessToken(token: string | null) { accessToken = token }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30000)
  const requestToken = accessToken
  try {
    const headers: Record<string, string> = {}
    if (requestToken) headers.Authorization = `Bearer ${requestToken}`
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}${path}`, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: 'no-store',
    })
    if (response.status === 204) return undefined as T
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      if (response.status === 401 && requestToken && requestToken === accessToken) window.dispatchEvent(new Event('session-expired'))
      const details = Array.isArray(data.errors) ? data.errors.map((item: { field: string; message: string }) => `${item.field.replace('body.', '')}: ${item.message}`).join(' · ') : ''
      throw new ApiError(`${typeof data.detail === 'string' ? data.detail : 'No se pudo completar la solicitud.'}${details ? ` ${details}` : ''}`, response.status)
    }
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new Error(error instanceof DOMException && error.name === 'AbortError'
      ? 'La solicitud tardó demasiado. Intenta nuevamente.' : 'No se pudo conectar con la API. Comprueba que esté iniciada.')
  } finally { window.clearTimeout(timeout) }
}

export const tenantPath = (tenantId: string) => `/tenants/${tenantId}`
export const mailboxPath = (tenantId: string, mailboxId: string) => `${tenantPath(tenantId)}/mailboxes/${mailboxId}`
export const messageOf = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la operación.'
export const statusName = (status: string) => ({ active: 'Activo', pending: 'Por verificar', disabled: 'Deshabilitado', error: 'Revisar conexión' }[status] || status)
