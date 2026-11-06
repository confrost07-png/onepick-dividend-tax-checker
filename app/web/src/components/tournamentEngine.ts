// 법 토너먼트: 회사 하나 = 동전 하나. 조세특례제한법 제104조의27 ①의 문 세 개를 라운드로 지난다.
// 1라운드 자료 확인 → 2라운드 제2호(배당이 줄지 않았나) → 3라운드 제3호(가목 언덕 또는 나목 계단).
// 동전 수는 모두 /api/judgement/funnel(core.core_judgement_2026) 값이다.
import type { Funnel, Status } from '../api'
import { moaSrc } from '../util'
import type { Mood } from '../util'

type Res = Status
type Move =
  | { t: 'wait'; at: number; jig?: boolean }
  | { t: 'roll' | 'drop' | 'hop'; to: [number, number]; sp?: number; h?: number; fx?: Fx; i?: boolean; x0?: number; y0?: number; p?: number; dur?: number }
type Fx = 'dust' | 'pit' | 'gold' | 'yellow'
interface Coin { x: number; y: number; jy: number; res: Res; m: Move[]; done: boolean; hl: number; spin: number; bob: number }
interface Part { x: number; y: number; vx: number; vy: number; life: number; col: string; size: number; g: number; star?: boolean; conf?: boolean; rot?: number }

const W = 1000, H = 600, LT = 400, LB = 450, R = 3.7
const PH = { r1: 2.6, r2: 8.4, r3: 13.4, end: 20.5 }
const CAM: [number, number, number, number][] = [[0, 500, 300, 1], [PH.r1, 300, 380, 1.5], [PH.r2 + .2, 500, 430, 1.55], [PH.r3 + .2, 760, 320, 1.28], [PH.end - 1.2, 500, 300, 1]]
const COIN: Record<Res, [string, string]> = { '충족': ['#FFF0A8', '#E8A800'], '미충족': ['#FFB3B5', '#D93A40'], '판정 보류': ['#E3E7ED', '#8B95A5'] }
const CHIP: Record<Res, string> = { '충족': '#3D6BFF', '미충족': '#F2555A', '판정 보류': '#8B95A5' }
const rnd = (a: number, b: number) => a + Math.random() * (b - a)
const laneY = () => LT + 8 + Math.random() * (LB - LT - 16)

function piler(x0: number, x1: number, baseY: number, sp: number) {
  let k = 0
  const cols = Math.floor((x1 - x0) / sp)
  return (): [number, number] => { const c = k % cols, r = Math.floor(k / cols); k++; return [x0 + c * sp + (r % 2) * sp / 2 + sp / 2, baseY - r * sp * .8] }
}

export interface TournamentOpts { autoplay?: 'visible' | 'none'; still?: boolean; onDone?: () => void }

export function mountTournament(host: HTMLElement, F: Funnel, opts: TournamentOpts = {}): () => void {
  host.innerHTML = '<canvas aria-hidden="true"></canvas><div class="t-moa"><img alt=""><div class="t-say" aria-live="polite"></div></div><div class="t-board"></div><button class="t-play">▶ 토너먼트 시작</button>'
  const cv = host.querySelector('canvas')!, ctx = cv.getContext('2d')!
  const say = host.querySelector<HTMLDivElement>('.t-say')!, moa = host.querySelector('img')!
  const board = host.querySelector<HTMLDivElement>('.t-board')!, play = host.querySelector<HTMLButtonElement>('.t-play')!
  const met = F.ga + F.na + F.na_deficit, fail = F.fail2 + F.fail3, hold = F.hold_missing + F.hold_zero
  const LINES: [number, Mood, string, [string, string, string] | null][] = [
    [0, 'base', `동전 ${F.total}개가 출발선에 섰어요. 동전 하나가 회사 하나예요. 문 세 개를 지나야 분리과세 대상이 돼요!`, null],
    [PH.r1, 'curious', `1라운드! 판정에 필요한 숫자가 다 있는지 봐요. 숫자가 빠진 ${F.hold_missing}곳은 대기석으로!`, ['ROUND 1', '숫자가 다 있나', '#6B7684']],
    [PH.r2, 'sad', `2라운드, 제2호예요. 배당소득이 2024년보다 줄면 40%를 넘었어도 여기서 끝! ${F.fail2}곳이 구덩이로…`, ['ROUND 2', '제2호 · 배당이 줄지 않았나', '#F2555A']],
    [PH.r3, 'curious', '3라운드, 제3호 갈림길! 배당성향 40% 이상이면 가목 언덕으로 폴짝, 25% 이상이면서 배당을 10% 이상 늘렸으면 나목 계단으로 깡충.', ['ROUND 3', '제3호 · 가목 또는 나목', '#3D6BFF']],
    [PH.end, 'happy', `${met}곳 통과! 문 세 개는 "모두" 지나야 하고, 마지막 문만 "둘 중 하나"면 돼요. 대기석 ${hold}곳은 확인이 끝나면 다시 달려요.`, ['FINISH', `충족 ${met} · 미충족 ${fail} · 보류 ${hold}`, '#19B36B']],
  ]
  const GROUPS: { key: string; n: number; res: Res }[] = [
    { key: 'hold1', n: F.hold_missing, res: '판정 보류' }, { key: 'fail2', n: F.fail2, res: '미충족' },
    { key: 'ga', n: F.ga, res: '충족' }, { key: 'na', n: F.na + F.na_deficit, res: '충족' },
    { key: 'hold3', n: F.hold_zero, res: '판정 보류' }, { key: 'fail3', n: F.fail3, res: '미충족' }]

  let coins: Coin[] = [], parts: Part[] = [], counts: Record<Res, number> = { '충족': 0, '미충족': 0, '판정 보류': 0 }
  let sim = 0, playing = false, shown = -1, shake = 0, raf = 0, last: number | null = null, tick = 0, finished = false
  let banner: { t: number; big: string; small: string; bg: string } | null = null
  let cam = { x: 500, y: 300, z: 1 }
  const gate = [0, 0, 0]
  let base = 1

  const fit = () => { const d = window.devicePixelRatio || 1, w = cv.clientWidth || 800; cv.width = w * d; cv.height = w * H / W * d; base = cv.width / W }
  window.addEventListener('resize', fit); fit()

  function build() {
    const s = { start: piler(20, 205, 445, 7.4), b1: piler(165, 335, 548, 7.6), b2: piler(625, 785, 548, 7.6), pit: piler(492, 598, 550, 7.6), ga: piler(838, 992, 198, 7.2), na: piler(690, 818, 338, 7.2) }
    coins = []; parts = []; counts = { '충족': 0, '미충족': 0, '판정 보류': 0 }; shake = 0; banner = null; gate.fill(0); finished = false
    const list: typeof GROUPS = []
    GROUPS.forEach(g => { for (let i = 0; i < g.n; i++) list.push(g) })
    for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]] }
    let q1 = 0, q2 = 0, q3 = 0
    list.forEach(g => {
      const p = s.start(), m: Move[] = []
      m.push({ t: 'wait', at: PH.r1 + q1++ * .0045 }, { t: 'roll', to: [230, laneY()], sp: 520 })
      if (g.key === 'hold1') m.push({ t: 'roll', to: [rnd(250, 290), 470] }, { t: 'drop', to: s.b1(), fx: 'dust' })
      else {
        m.push({ t: 'roll', to: [rnd(300, 450), laneY()] }, { t: 'wait', at: PH.r2 + q2++ * .0045, jig: true }, { t: 'roll', to: [470, laneY()], sp: 520 })
        if (g.key === 'fail2') m.push({ t: 'roll', to: [rnd(495, 520), 462] }, { t: 'drop', to: s.pit(), fx: 'pit' })
        else {
          m.push({ t: 'roll', to: [rnd(505, 610), laneY()] }, { t: 'wait', at: PH.r3 + q3++ * .0045, jig: true }, { t: 'roll', to: [630, laneY()], sp: 520 })
          if (g.key === 'ga') m.push({ t: 'hop', to: s.ga(), h: rnd(150, 210), fx: 'gold' })
          else if (g.key === 'na') m.push({ t: 'hop', to: [662, 380], h: 16 }, { t: 'hop', to: [680, 358], h: 16 }, { t: 'hop', to: [700, 338], h: 18 }, { t: 'roll', to: s.na(), fx: 'yellow' })
          else if (g.key === 'hold3') m.push({ t: 'roll', to: [rnd(640, 700), 470] }, { t: 'drop', to: s.b2(), fx: 'dust' })
          else m.push({ t: 'roll', to: [600, 462] }, { t: 'drop', to: s.pit(), fx: 'pit' })
        }
      }
      coins.push({ x: p[0], y: p[1], jy: 0, res: g.res, m, done: false, hl: 0, spin: Math.random() * 6, bob: Math.random() * 6 })
    })
  }

  function burst(x: number, y: number, k: Fx) {
    if (opts.still) return
    const n = k === 'pit' ? 10 : k === 'gold' ? 6 : k === 'yellow' ? 3 : 4
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 6.28, v = k === 'pit' ? rnd(60, 180) : rnd(30, 110)
      parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - (k === 'pit' ? 120 : 60), life: 1,
        col: k === 'pit' ? '#F2555A' : k === 'gold' ? '#FFC93C' : k === 'yellow' ? '#FFD866' : '#B8C0CC',
        size: k === 'gold' ? rnd(2, 4) : rnd(1.5, 3), star: k === 'gold', g: k === 'pit' ? 380 : 220 })
    }
    if (k === 'pit') shake = Math.min(10, shake + 2.2)
  }
  function confetti() {
    const P = ['#3D6BFF', '#FFC93C', '#19B36B', '#F2555A', '#9DB4FF']
    for (let i = 0; i < 220; i++) parts.push({ x: rnd(0, W), y: rnd(-200, -10), vx: rnd(-40, 40), vy: rnd(40, 140), life: 2.6, col: P[i % 5], size: rnd(3, 6), conf: true, rot: Math.random() * 6, g: 60 })
  }

  function step(c: Coin, now: number, dt: number) {
    while (c.m.length) {
      const v = c.m[0]
      if (v.t === 'wait') {
        if (now >= v.at) { c.m.shift(); continue }
        if (v.jig) { c.bob += dt * 14; c.jy = Math.abs(Math.sin(c.bob)) * 1.6 }
        return
      }
      c.jy = 0
      if (!v.i) {
        v.i = true; v.x0 = c.x; v.y0 = c.y; v.p = 0
        const d = Math.hypot(v.to[0] - c.x, v.to[1] - c.y)
        v.dur = v.t === 'roll' ? Math.max(.06, d / (v.sp || 430)) : v.t === 'drop' ? Math.max(.22, Math.sqrt(Math.abs(v.to[1] - c.y) / 900) * 1.3) : (v.h ?? 0) > 60 ? .85 : .16
      }
      v.p = Math.min(1, v.p! + dt / v.dur!)
      const p = v.p, x0 = v.x0!, y0 = v.y0!
      if (v.t === 'roll') { c.x = x0 + (v.to[0] - x0) * p; c.y = y0 + (v.to[1] - y0) * p - Math.abs(Math.sin(p * Math.PI * 3)) * 2.5; c.spin += dt * 16 }
      else if (v.t === 'drop') { c.x = x0 + (v.to[0] - x0) * p; c.y = y0 + (v.to[1] - y0) * p * p; c.spin += dt * 24 }
      else { const e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2; c.x = x0 + (v.to[0] - x0) * e; c.y = y0 + (v.to[1] - y0) * e - Math.sin(p * Math.PI) * (v.h ?? 0); c.spin += dt * 20 }
      if (p >= 1) { c.m.shift(); c.x = v.to[0]; c.y = v.to[1]; if (v.fx) burst(c.x, c.y, v.fx); continue }
      return
    }
    if (!c.done) { c.done = true; c.hl = 1; counts[c.res]++; bump(c.res) }
  }

  const label = (s: string, x: number, y: number, col = '#191F28', size = 13, w = 800) => {
    ctx.fillStyle = col; ctx.font = `${w} ${size}px "Gothic A1",sans-serif`; ctx.textAlign = 'center'; ctx.fillText(s, x, y)
  }
  const rr = (x: number, y: number, w: number, h: number, r: number) => {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.fill()
  }
  const block = (x0: number, x1: number, top: number, dep: number, bot: number, tc: string, fc: string) => {
    ctx.fillStyle = fc; ctx.fillRect(x0, top + dep, x1 - x0, bot - top - dep); ctx.fillStyle = tc; ctx.fillRect(x0, top, x1 - x0, dep)
  }
  function drawGate(i: number, x: number, name: string, sub: string, on: boolean, now: number) {
    const glow = on ? .5 + .5 * Math.sin(now * 8) : 0
    ctx.save(); ctx.lineCap = 'round'
    if (on) { ctx.shadowColor = '#FFC93C'; ctx.shadowBlur = 18 * glow }
    ctx.lineWidth = 7; ctx.strokeStyle = on ? '#FFC93C' : '#C5CCD6'
    ctx.beginPath(); ctx.moveTo(x - 24, LB); ctx.lineTo(x - 24, LT - 52); ctx.arc(x, LT - 52, 24, Math.PI, 0); ctx.lineTo(x + 24, LB); ctx.stroke(); ctx.restore()
    ctx.save(); ctx.beginPath(); ctx.rect(x - 21, LT - 74, 42, LB - LT + 74); ctx.clip()
    const lift = gate[i] * (LB - LT + 80); ctx.fillStyle = 'rgba(25,31,40,.55)'
    for (let k = -2; k <= 2; k++) ctx.fillRect(x + k * 8 - 1.5, LT - 74 - lift, 3, LB - LT + 74)
    ctx.restore()
    label(name, x, LT - 90, on ? '#2547D9' : '#6B7684', 13); label(sub, x, LT - 74, '#6B7684', 11, 600)
  }
  function stage(now: number) {
    ctx.fillStyle = '#D3DAEA'; ctx.fillRect(-200, LB, 840, 24); ctx.fillStyle = '#F3F5FA'; ctx.fillRect(-200, LT, 840, LB - LT)
    ctx.strokeStyle = '#E0E5EF'; ctx.setLineDash([10, 10]); ctx.lineDashOffset = -now * 60
    ctx.beginPath(); ctx.moveTo(-200, (LT + LB) / 2); ctx.lineTo(640, (LT + LB) / 2); ctx.stroke(); ctx.setLineDash([])
    label(`출발선 · ${F.total}곳`, 112, 392, '#6B7684', 12)
    for (const [a, b, s] of [[160, 340, '대기석 · 판정 보류 (자료 확인 중)'], [620, 790, '대기석 · 판정 보류 (전전년 무배당)']] as const) {
      ctx.fillStyle = '#E4E8EE'; rr(a, 515, b - a, 45, 14); label(s, (a + b) / 2, 580, '#8B95A5', 11)
    }
    ctx.fillStyle = '#2E2326'; rr(486, 470, 118, 92, 18)
    ctx.fillStyle = `rgba(242,85,90,${.15 + .1 * Math.sin(now * 5)})`; rr(486, 470, 118, 92, 18)
    label('구덩이 · 미충족', 545, 582, '#F2555A', 11)
    ctx.fillStyle = '#FFE9A8'; for (const [a, b, y] of [[640, 690, 380], [662, 690, 360]]) ctx.fillRect(a, y, b - a, LB - y)
    block(685, 822, 330, 16, LB + 24, '#FFD866', '#FFE9A8'); label('나목 계단', 752, 372, '#9a6b00', 13); label('25% 이상 + 배당 10%↑', 752, 388, '#9a6b00', 10, 600)
    block(836, 994, 190, 16, LB + 24, '#9DB4FF', '#C9D6FF'); label('가목 언덕', 915, 236, '#2547D9', 14); label('배당성향 40% 이상', 915, 253, '#2547D9', 11, 600)
    const r = !playing ? 0 : now < PH.r1 ? 0 : now < PH.r2 ? 1 : now < PH.r3 ? 2 : now < PH.end ? 3 : 0
    drawGate(0, 230, '1라운드', '숫자 다 있나', r === 1, now)
    drawGate(1, 470, '2라운드 · 제2호', '배당이 줄지 않았나', r === 2, now)
    drawGate(2, 630, '3라운드 · 제3호', '가목 또는 나목', r === 3, now)
  }
  function drawCoin(c: Coin) {
    const cols = c.done ? COIN[c.res] : COIN['충족'], y = c.y - c.jy, w = Math.max(.9, Math.abs(Math.cos(c.spin)) * R)
    ctx.fillStyle = cols[1]; ctx.beginPath(); ctx.ellipse(c.x, y, w + .6, R, 0, 0, 7); ctx.fill()
    ctx.fillStyle = cols[0]; ctx.beginPath(); ctx.ellipse(c.x - .4, y - .4, w * .75, R * .75, 0, 0, 7); ctx.fill()
    if (c.hl > 0) {
      ctx.strokeStyle = `rgba(255,255,255,${c.hl})`; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(c.x, y, R + 4 * (1 - c.hl) + 1, 0, 7); ctx.stroke()
      c.hl = Math.max(0, c.hl - .035)
    }
  }
  function drawParts(dt: number) {
    parts = parts.filter(p => p.life > 0)
    for (const p of parts) {
      p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt * (p.conf ? .45 : 1.6)
      ctx.globalAlpha = Math.max(0, Math.min(1, p.life)); ctx.fillStyle = p.col
      if (p.conf) { p.rot! += dt * 8; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot!); ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2); ctx.restore() }
      else if (p.star) { ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.life * 4); ctx.fillRect(-p.size / 2, -.6, p.size, 1.2); ctx.fillRect(-.6, -p.size / 2, 1.2, p.size); ctx.restore() }
      else { ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, 7); ctx.fill() }
    }
    ctx.globalAlpha = 1
  }
  function drawBanner(now: number) {
    if (!banner) return
    const t = now - banner.t
    if (t > 1.8) { banner = null; return }
    const a = Math.min(1, t / .25), o = t > 1.4 ? (t - 1.4) / .4 : 0, x = W / 2 + (1 - a) * -400 + o * 400
    ctx.globalAlpha = 1 - o; ctx.fillStyle = banner.bg; rr(x - 210, H * .36, 420, 78, 39)
    label(banner.big, x, H * .36 + 38, '#fff', 30); label(banner.small, x, H * .36 + 62, 'rgba(255,255,255,.9)', 14, 700); ctx.globalAlpha = 1
  }
  function countdown(now: number) {
    if (!playing || now >= PH.r1 || now < .6) return
    const n = now < 1.2 ? '3' : now < 1.8 ? '2' : now < 2.4 ? '1' : '출발!', f = (now * 1000 % 600) / 600
    ctx.globalAlpha = 1 - f * .6; ctx.save(); ctx.translate(W / 2, H * .45); ctx.scale(1.6 - f * .6, 1.6 - f * .6)
    label(n, 0, 0, n === '출발!' ? '#3D6BFF' : '#191F28', 64); ctx.restore(); ctx.globalAlpha = 1
  }
  function talk(now: number) {
    let k = 0
    LINES.forEach((l, i) => { if (now >= l[0]) k = i })
    if (k === shown) return
    shown = k
    say.style.opacity = '0'
    setTimeout(() => { say.textContent = LINES[k][2]; say.style.opacity = '1' }, 160)
    moa.src = moaSrc(LINES[k][1]); moa.className = ''; void moa.offsetWidth; moa.className = LINES[k][1] === 'sad' ? 'shake' : 'jump'
    const b = LINES[k][3]
    if (b && !opts.still) banner = { t: now, big: b[0], small: b[1], bg: b[2] }
    if (k === LINES.length - 1) { if (!opts.still) confetti(); if (!finished) { finished = true; showAgain(); opts.onDone?.() } }
  }
  function renderBoard() {
    const live = coins.length - counts['충족'] - counts['미충족'] - counts['판정 보류']
    board.innerHTML = `<div style="background:#fff">달리는 중 ${live}</div>` +
      (Object.keys(CHIP) as Res[]).map(k => `<div data-c="${k}" style="background:${CHIP[k]};color:#fff">${k} ${counts[k]}</div>`).join('')
  }
  function bump(k: Res) {
    const el = board.querySelector<HTMLDivElement>(`[data-c="${k}"]`)
    if (el) { el.style.transform = 'scale(1.18)'; setTimeout(() => { el.style.transform = '' }, 110) }
  }
  function showAgain() {
    if (host.querySelector('.t-again')) return
    const again = document.createElement('button')
    again.className = 't-again'; again.textContent = '↻ 다시 보기'
    again.onclick = () => { again.remove(); start() }
    host.appendChild(again)
  }
  function frame(ts: number) {
    if (last === null) last = ts
    const rdt = Math.min(.1, (ts - last) / 1000); last = ts
    if (playing) sim += rdt
    let tg = CAM[0]
    if (playing) CAM.forEach(c => { if (sim >= c[0]) tg = c })
    const k = 1 - Math.pow(.04, rdt)
    cam.x += (tg[1] - cam.x) * k; cam.y += (tg[2] - cam.y) * k; cam.z += (tg[3] - cam.z) * k
    const hw = W / 2 / cam.z, hh = H / 2 / cam.z
    const cx = Math.max(hw, Math.min(W - hw, cam.x)), cy = Math.max(hh, Math.min(H - hh, cam.y))
    ;[PH.r1, PH.r2, PH.r3].forEach((t, i) => { gate[i] += ((playing && sim >= t ? 1 : 0) - gate[i]) * Math.min(1, rdt * 5) })
    shake *= Math.pow(.02, rdt)
    ctx.setTransform(base, 0, 0, base, 0, 0); ctx.clearRect(0, 0, W, H); ctx.save()
    ctx.translate(W / 2 + (Math.random() - .5) * shake, H / 2 + (Math.random() - .5) * shake); ctx.scale(cam.z, cam.z); ctx.translate(-cx, -cy)
    stage(sim)
    if (playing) coins.forEach(c => step(c, sim, rdt))
    ;[...coins].sort((a, b) => a.y - b.y).forEach(drawCoin)
    drawParts(rdt); ctx.restore()
    drawBanner(sim); countdown(sim)
    if (playing) talk(sim)
    if ((tick += rdt) > .06) { tick = 0; renderBoard() }
    raf = requestAnimationFrame(frame)
  }
  function start() { build(); sim = 0; shown = -1; playing = true; cam = { x: 500, y: 300, z: 1 }; play.hidden = true }

  play.onclick = start
  build(); renderBoard(); say.textContent = LINES[0][2]; moa.src = moaSrc('base')
  let observer: IntersectionObserver | null = null
  if (opts.still) {
    build(); playing = true
    for (let t = 0; t < PH.end + 4; t += .02) { sim = t; coins.forEach(c => step(c, sim, .02)) }
    play.hidden = true; talk(sim); gate.fill(1)
  } else if (opts.autoplay === 'visible') {
    observer = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && !playing) { start(); observer?.disconnect() } }), { threshold: .35 })
    observer.observe(host)
  }
  raf = requestAnimationFrame(frame)
  return () => { cancelAnimationFrame(raf); observer?.disconnect(); window.removeEventListener('resize', fit); host.innerHTML = '' }
}
