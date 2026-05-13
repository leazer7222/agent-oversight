/**
 * Shared pagination utilities for read API routes.
 */

export interface PaginationParams {
  limit: number
  offset: number
}

export interface PaginationMeta {
  limit: number
  offset: number
  has_more: boolean
}

const MAX_LIMIT = 200
const DEFAULT_LIMIT = 50

export function parsePagination(url: URL): PaginationParams {
  const limit = Math.min(
    parseInt(url.searchParams.get('limit') ?? String(DEFAULT_LIMIT), 10) || DEFAULT_LIMIT,
    MAX_LIMIT
  )
  const offset = Math.max(parseInt(url.searchParams.get('offset') ?? '0', 10) || 0, 0)
  return { limit, offset }
}

export function paginationMeta(params: PaginationParams, returned: number): PaginationMeta {
  return {
    limit: params.limit,
    offset: params.offset,
    has_more: returned === params.limit,
  }
}
