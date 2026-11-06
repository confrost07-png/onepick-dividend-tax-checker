// 웹 화면의 뼈대: 위쪽 메뉴·회사 찾기·로그인 메뉴와 주소(라우트)별 화면 연결, 탭 제목.
import { useEffect } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import Search from './components/Search'
import Check from './pages/Check'
import Column from './pages/Column'
import Company from './pages/Company'
import Consult from './pages/Consult'
import Home from './pages/Home'
import IsaIrp from './pages/IsaIrp'
import Legal from './pages/Legal'
import Me from './pages/Me'
import MyPage from './pages/MyPage'
import Story from './pages/Story'
import Wealth from './pages/Wealth'
import AccountMenu from './components/AccountMenu'

const TITLES: Record<string, string> = { '/': '홈', '/check': '내 배당 점검', '/analysis': '데이터 이야기', '/column': '금융 상식 칼럼', '/wealth': 'A은행 자산관리', '/consult': '세무상담 신청', '/isa-irp': '제도별 비교', '/me': '내 정보', '/mypage': '마이페이지', '/privacy': '개인정보 처리 안내', '/terms': '이용약관(특약)' }

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
    if (!pathname.startsWith('/column/')) document.title = `${TITLES[pathname] ?? (pathname.startsWith('/company/') ? '회사 보기' : '찾는 화면이 없어요')} · 원픽`
    // 좁은 화면에서는 메뉴가 옆으로 밀리므로, 지금 메뉴가 보이게 당겨 둔다
    document.querySelector('.nav a.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [pathname])
  return (
    <>
      <header className="top">
        <div className="wrap">
          <Link className="logo" to="/"><i />원픽</Link>
          <nav className="nav" aria-label="주 메뉴">
            <NavLink to="/" end>홈</NavLink>
            <NavLink to="/check">내 배당 점검</NavLink>
            {/* 메뉴는 어느 화면에서나 같게 둔다. 기획안 원칙(챗봇과 분석을 잇지 않음)은 점검 결과 안에 분석 링크를 넣지 않는 것으로 지킨다 */}
            <NavLink to="/analysis">데이터 이야기</NavLink>
            <NavLink to="/column">금융 상식</NavLink>
            <NavLink to="/wealth" className={({ isActive }) => (isActive || pathname === '/consult' ? 'active' : '')}>자산관리</NavLink>
            <NavLink to="/isa-irp">제도별 비교</NavLink>
          </nav>
          <Search slashKey />
          <AccountMenu />
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/analysis" element={<Story />} />
          <Route path="/company/:code" element={<Company />} />
          <Route path="/check" element={<Check />} />
          <Route path="/column" element={<Column />} />
          <Route path="/wealth" element={<Wealth />} />
          <Route path="/consult" element={<Consult />} />
          <Route path="/isa-irp" element={<IsaIrp />} />
          <Route path="/me" element={<Me />} />
          <Route path="/mypage" element={<MyPage />} />
          <Route path="/privacy" element={<Legal kind="privacy" />} />
          <Route path="/terms" element={<Legal kind="terms" />} />
          <Route path="/column/:id" element={<Column />} />
          <Route path="*" element={<div className="wrap loading">찾는 화면이 없어요. <Link to="/">홈으로</Link></div>} />
        </Routes>
      </main>
      <footer className="wrap foot small">
        <p>종목 추천이 아니며 매수·매도 판단 근거로 제공하지 않습니다. 세액은 참고용 모의 계산이에요(확정 세액·환급액 아님). 상담 신청·예약·로그인은 시연용 모형이에요. 판정은 공식 해설 전까지 '현재 해석 기준'이에요.</p>
        <p>자료: OpenDART · KIND · 국가법령정보센터 (조세특례제한법 제104조의27, 시행 2026. 9. 18.)</p>
        <p className="foot-links">원픽은 A은행(가상) 앱의 애드온 서비스로, A은행 개인(신용)정보처리방침과 기본약관을 따릅니다 · <Link to="/privacy"><b>원픽 개인정보 처리 안내</b></Link> · <Link to="/terms">이용약관(특약)</Link></p>
      </footer>
    </>
  )
}
