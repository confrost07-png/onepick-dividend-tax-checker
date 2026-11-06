// 세무상담·신고대행 신청 (/consult): 종류 → 방법 → 지점 → 날짜·시간 → 점검 결과 보내기 → 확인 → 완료(모형).
// 개인정보를 받지 않고, 신청 내용을 서버로 보내지 않는다. 로그인(시연용 고객)했으면 마이페이지에서 보고 취소할 수 있게
// 신청 내역을 이 브라우저에만 남긴다(applications.ts).
import { useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { BANK, BRANCHES, CONSULT_TYPES, MOCK_NOTE, SAVED_NOTE, REGIONS, SLOTS, WAYS, dateText, dayName, isTaken, mockNumber, nextBusinessDays } from '../bank'
import type { ConsultType, Region, Way } from '../bank'
import { addApp } from '../applications'
import { usePersona } from '../persona'
import { api } from '../api'
import { moaSrc, useLoad } from '../util'

export interface CheckupSummary { headline: string; diff: string | null; stocks: string[] }

const STEPS = ['상담 종류', '상담 방법', '지점', '날짜·시간', '점검 결과', '확인']

export default function Consult() {
  const [params] = useSearchParams()
  const checkup = (useLocation().state as { checkup?: CheckupSummary; send?: boolean } | null) ?? {}
  const [type, setType] = useState<ConsultType | null>((params.get('type') as ConsultType) || null)
  const [way, setWay] = useState<Way | null>((params.get('way') as Way) || null)
  const [branch, setBranch] = useState<string | null>(params.get('branch'))
  const [region, setRegion] = useState<Region | '전체'>('전체')
  const [date, setDate] = useState<Date | null>(null)
  const [slot, setSlot] = useState<string | null>(null)
  const [send, setSend] = useState(!!checkup.send)
  const [agree, setAgree] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [savedFor, setSavedFor] = useState<string | null>(null) // 신청할 때 로그인해 있던 고객(내역은 이 고객 마이페이지에 남음)
  const { id: who } = usePersona()
  const { data: people } = useLoad(api.personas)
  const me = people?.find(p => p.id === who)
  const firstOpen = type ? (way ? (way === 'phone' || branch ? 3 : 2) : 1) : 0
  const [step, setStep] = useState(firstOpen)

  const days = useMemo(() => nextBusinessDays(10), [])
  const br = BRANCHES.find(b => b.id === branch)
  const branchesForWay = BRANCHES.filter(b => way !== 'video' || b.video).filter(b => region === '전체' || b.region === region)
  const dayOk = (d: Date) => way === 'phone' || !br || br.days.includes(dayName(d))
  const canNext = [!!type, !!way, way === 'phone' || !!br, !!date && !!slot, !send || agree, true][step]
  const where = way === 'phone' ? `${BANK} 세무상담센터(전화)` : br ? `${BANK} PB센터 ${br.name}점${way === 'video' ? '(화상)' : ''}` : '–'
  const typeName = CONSULT_TYPES.find(t => t.id === type)?.name

  function submit() {
    const no = mockNumber()
    if (who && type && way && date && slot) {
      setSavedFor(who)
      setSaved(addApp(who, {
        no, type, typeName: typeName ?? '', way, wayName: WAYS.find(w => w.id === way)?.name ?? '', where,
        date: date.toISOString(), slot, send, createdAt: new Date().toISOString(), status: '신청',
      }))
    }
    setDone(no)
  }
  const go = (n: number) => { setStep(n); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const next = () => go(way === 'phone' && step === 1 ? 3 : step + 1)
  const back = () => go(way === 'phone' && step === 3 ? 1 : step - 1)

  if (done) {
    return (
      <div className="wrap consult">
        <div className="card done-card">
          <img src={moaSrc('happy')} alt="" />
          <span className="tag">모형 예약</span>
          <h1>모형 예약을 마쳤어요</h1>
          <dl className="facts" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div><dt>예약 번호(모형)</dt><dd>{done}</dd></div>
            <div><dt>상담</dt><dd>{typeName}</dd></div>
            <div><dt>곳</dt><dd>{where}</dd></div>
            <div><dt>때</dt><dd>{date && dateText(date)} {slot}</dd></div>
          </dl>
          <p>{send ? '점검 결과를 함께 보내는 것으로 표시했어요(모형).' : '점검 결과는 보내지 않고 예약만 했어요.'} 실제 서비스라면 {BANK} 앱 알림과 문자로 확정 안내가 가요.</p>
          {savedFor
            ? <p>{saved ? <><b>마이페이지</b>에서 신청 내역을 확인하고 취소할 수 있어요.</> : '이 브라우저에 신청 내역을 남기지 못했어요(저장소를 쓸 수 없음).'}</p>
            : <p className="small">로그인하지 않고 신청해서 내역이 남지 않아요. 위쪽 메뉴에서 로그인하고 신청하면 마이페이지에서 확인·취소할 수 있어요.</p>}
          <p className="small">{savedFor && saved ? SAVED_NOTE : MOCK_NOTE}</p>
          <div className="chips">{savedFor && saved && savedFor === who && <Link className="btn" to="/mypage">마이페이지에서 보기</Link>}<Link className={savedFor && saved && savedFor === who ? 'btn btn--soft' : 'btn'} to="/wealth">자산관리서비스로</Link><Link className="btn btn--soft" to="/check">점검으로 돌아가기</Link></div>
        </div>
      </div>
    )
  }

  return (
    <div className="wrap consult">
      <header className="check-head">
        <span className="bank-mark">{BANK}</span>
        <h1>세무상담 신청</h1>
        <p className="small" style={{ margin: 0 }}>{MOCK_NOTE}</p>
      </header>
      <ol className="consult-steps" aria-label="신청 단계">
        {STEPS.map((s, i) => (
          <li key={s} className={i < step ? 'done' : i === step ? 'now' : ''}>
            <button disabled={i > step || (way === 'phone' && i === 2)} onClick={() => go(i)}><span>{i + 1}</span>{s}</button>
          </li>
        ))}
      </ol>

      <section className="card consult-card" aria-live="polite">
        {step === 0 && <>
          <h2>어떤 상담이 필요하세요?</h2>
          <div className="pick-list">
            {CONSULT_TYPES.map(t => (
              <button key={t.id} className={`pick ${type === t.id ? 'on' : ''}`} aria-pressed={type === t.id} onClick={() => setType(t.id)}>
                <b>{t.name}</b><span>{t.line}</span>
              </button>
            ))}
          </div>
        </>}

        {step === 1 && <>
          <h2>어떻게 상담할까요?</h2>
          <div className="pick-list pick-list--3">
            {WAYS.map(w => (
              <button key={w.id} className={`pick ${way === w.id ? 'on' : ''}`} aria-pressed={way === w.id} onClick={() => { setWay(w.id); if (w.id === 'video' && br && !br.video) setBranch(null) }}>
                <b>{w.name}</b><span>{w.line}</span>
              </button>
            ))}
          </div>
        </>}

        {step === 2 && <>
          <h2>어느 PB센터에서 할까요?</h2>
          {way === 'video' && <p className="small">화상 상담이 되는 지점만 보여 드려요.</p>}
          <div className="chips" role="group" aria-label="지역 고르기" style={{ marginBottom: 12 }}>
            {(['전체', ...REGIONS] as const).map(r => <button key={r} className="chip" aria-pressed={region === r} onClick={() => setRegion(r)} style={region === r ? { background: 'var(--sea)', color: '#fff' } : undefined}>{r}</button>)}
          </div>
          <div className="pick-list pick-list--grid">
            {branchesForWay.map(b => (
              <button key={b.id} className={`pick ${branch === b.id ? 'on' : ''}`} aria-pressed={branch === b.id} onClick={() => { setBranch(b.id); setDate(null); setSlot(null) }}>
                <b>{b.name}점</b><span>{b.area}</span><span className="pick-days">세무 상담 {b.days.join('·')}</span>
              </button>
            ))}
            {branchesForWay.length === 0 && <p className="small">이 지역에는 화상 상담 지점이 없어요. 다른 지역을 골라 주세요.</p>}
          </div>
        </>}

        {step === 3 && <>
          <h2>언제가 좋으세요?</h2>
          <p className="small">{way === 'phone' ? '평일 아무 날이나 고를 수 있어요.' : `${br?.name}점은 ${br?.days.join('·')}요일에 세무 전문가가 있어요.`} 회색 시간은 이미 찼어요(모형).</p>
          <div className="date-row">
            {days.map(d => {
              const ok = dayOk(d), on = date?.toDateString() === d.toDateString()
              return <button key={d.toISOString()} className={`date ${on ? 'on' : ''}`} disabled={!ok} aria-pressed={on} onClick={() => { setDate(d); setSlot(null) }}><b>{d.getDate()}</b><span>{dayName(d)}</span></button>
            })}
          </div>
          {date && (
            <div className="chips" style={{ marginTop: 14 }}>
              {SLOTS.map(s => {
                const taken = isTaken(branch ?? 'phone', date, s)
                return <button key={s} className="chip" disabled={taken} aria-pressed={slot === s} onClick={() => setSlot(s)} style={slot === s ? { background: 'var(--sea)', color: '#fff' } : taken ? { opacity: .35, textDecoration: 'line-through' } : undefined}>{s}</button>
              })}
            </div>
          )}
        </>}

        {step === 4 && <>
          <h2>점검 결과를 함께 보낼까요?</h2>
          {checkup.checkup ? (
            <div className="send-box">
              <p className="small" style={{ marginTop: 0 }}>실제 서비스라면 세무 전문가가 상담 전에 미리 봐요(시연판은 보내지 않아요). 보내지 않아도 상담은 똑같이 받을 수 있어요.</p>
              <div className="send-preview">
                <b>보낼 내용</b>
                <p>{checkup.checkup.headline}</p>
                {checkup.checkup.diff && <p>계산상 세액 차이(참고용 모의 계산): {checkup.checkup.diff}</p>}
                <p className="small">종목별 판정·최소 필요 배당액·세액 계산 근거. 이름·주민등록번호·계좌번호는 보내지 않아요.</p>
              </div>
              <label className="toggle"><input type="checkbox" checked={send} onChange={e => { setSend(e.target.checked); if (!e.target.checked) setAgree(false) }} /> 점검 결과 함께 보내기</label>
              {send && (
                <div className="consent">
                  <b>개인정보 제3자 제공 동의 (모형)</b>
                  <ul>
                    <li>받는 곳: {BANK} 제휴 세무법인</li>
                    <li>보내는 것: 위 점검 결과</li>
                    <li>쓰는 곳: 이번 세무상담 준비</li>
                    <li>보관 기간: 상담이 끝나면 지워요</li>
                  </ul>
                  <p className="small" style={{ margin: '0 0 8px' }}>동의하지 않아도 상담은 똑같이 받을 수 있어요. <Link to="/privacy#third-party">개인정보 처리 안내 제4조 보기</Link></p>
                  <label className="toggle"><input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} /> 위 내용에 동의해요(모형)</label>
                </div>
              )}
            </div>
          ) : (
            <p>지금은 보낼 점검 결과가 없어요. 결과 없이도 상담을 신청할 수 있어요. <Link to="/check">먼저 점검하기</Link></p>
          )}
        </>}

        {step === 5 && <>
          <h2>이대로 신청할까요?</h2>
          <dl className="facts" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div><dt>상담</dt><dd>{typeName}</dd></div>
            <div><dt>방법</dt><dd>{WAYS.find(w => w.id === way)?.name}</dd></div>
            <div><dt>곳</dt><dd>{where}</dd></div>
            <div><dt>때</dt><dd>{date && dateText(date)} {slot}</dd></div>
            <div><dt>점검 결과</dt><dd>{send ? '함께 보내기로 표시(모형)' : '보내지 않아요'}</dd></div>
            <div><dt>연락받을 곳</dt><dd>{me ? `${me.name}님 ${BANK} 로그인 정보로 연결(모형)` : `${BANK} 로그인 정보로 연결(모형)`}</dd></div>
          </dl>
          <p className="small">이름과 연락처는 묻지 않아요. 실제 서비스에서는 {BANK} 앱에 로그인한 정보로 이어져요. 신청하면 A은행 기본약관·개인(신용)정보처리방침과 원픽 <Link to="/terms">이용약관(특약)</Link>·<Link to="/privacy">개인정보 처리 안내</Link>에 따라 처리해요.</p>
        </>}

        <div className="consult-nav">
          {step > 0 && <button className="btn btn--soft" onClick={back}>이전</button>}
          {step < 5
            ? <button className="btn" disabled={!canNext} onClick={next}>다음</button>
            : <button className="btn" onClick={submit}>신청하기(모형)</button>}
        </div>
      </section>
    </div>
  )
}
