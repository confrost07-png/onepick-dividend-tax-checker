// 웹 시작 파일: React를 화면에 붙이고 주소 이동(BrowserRouter)과 공통 디자인(index.css)을 켠다.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { PersonaProvider } from './persona'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <PersonaProvider>
        <App />
      </PersonaProvider>
    </BrowserRouter>
  </StrictMode>,
)
