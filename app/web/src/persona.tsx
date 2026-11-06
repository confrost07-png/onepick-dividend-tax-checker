// 로그인했다고 가정한 시연용 고객(source/core/personas.py). 고른 사람은 이 브라우저에만 기억한다(서버에 저장하지 않음).
import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

const KEY = 'onepick.persona'
const DEFAULT = null // 처음엔 로그인하지 않은 상태. 로그인하지 않아도 모든 화면을 쓸 수 있다

function read(): string | null {
  try { return localStorage.getItem(KEY) || DEFAULT } catch { return DEFAULT }
}

const Ctx = createContext<{ id: string | null; setId: (id: string | null) => void }>({ id: null, setId: () => {} })

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [id, set] = useState<string | null>(read)
  const setId = (v: string | null) => { set(v); try { localStorage.setItem(KEY, v ?? '') } catch { /* 저장 못 해도 이번 화면에서는 유지 */ } }
  return <Ctx.Provider value={{ id, setId }}>{children}</Ctx.Provider>
}

export const usePersona = () => useContext(Ctx)
