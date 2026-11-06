import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { Branch, Item } from './types'
import { useAuth } from '../auth/AuthContext'

export function useBranches() {
  const { can } = useAuth()
  return useQuery({ queryKey: ['branches'], queryFn: () => api<Branch[]>('/branches'), enabled: can('branches.view') })
}

export function useUserLookup() {
  return useQuery({ queryKey: ['user-lookup'], queryFn: () => api<{ id: number; full_name: string }[]>('/users/lookup'),
    staleTime: 60_000 })
}

export function useItems() {
  return useQuery({ queryKey: ['items'], queryFn: () => api<Item[]>('/items') })
}
