// 금융 상식 칼럼 글마다 붙는 그림 기호. 글의 내용을 한눈에 떠올리게 하는 단순한 그림이다.
const S = { sea: '#3D6BFF', deep: '#2547D9', coin: '#FFC93C', coinDeep: '#E0A500', ink: '#191F28', no: '#F2555A', ok: '#19B36B', gray: '#8B95A5', paper: '#FFFFFF' }

const ICONS: Record<string, React.ReactNode> = {
  // 가게(주식)와 차용증(채권)
  stockbond: <>
    <path d="M14 30 L32 16 L50 30 Z" fill={S.sea} /><rect x="18" y="30" width="28" height="20" rx="2" fill={S.paper} stroke={S.sea} strokeWidth="3" />
    <rect x="28" y="38" width="8" height="12" fill={S.coin} />
    <rect x="44" y="34" width="14" height="18" rx="2" fill={S.paper} stroke={S.gray} strokeWidth="2.5" /><path d="M47 40h8M47 45h6" stroke={S.gray} strokeWidth="2" />
  </>,
  // 투표함
  rights: <>
    <rect x="16" y="30" width="32" height="22" rx="3" fill={S.sea} /><rect x="26" y="29" width="12" height="3" fill={S.deep} />
    <rect x="25" y="12" width="14" height="20" rx="2" fill={S.paper} stroke={S.ink} strokeWidth="2" transform="rotate(-8 32 22)" />
    <path d="M28 21l3 3 6-6" stroke={S.ok} strokeWidth="3" fill="none" strokeLinecap="round" transform="rotate(-8 32 22)" />
  </>,
  // 피자
  dividend: <>
    <circle cx="32" cy="32" r="20" fill="#FBE3B4" stroke="#E8B26A" strokeWidth="4" />
    <path d="M32 32 L32 12 A20 20 0 0 1 51 26 Z" fill={S.coin} transform="translate(3 -3)" />
    <circle cx="25" cy="38" r="3" fill={S.no} /><circle cx="36" cy="42" r="3" fill={S.no} /><circle cx="22" cy="27" r="3" fill={S.no} />
  </>,
  // 두 주머니
  pocket: <>
    <path d="M10 26 q0 -6 8 -6 h10 q8 0 8 6 v18 q0 8 -13 8 q-13 0 -13 -8 Z" fill={S.gray} opacity=".55" />
    <path d="M36 32 q0 -5 6 -5 h6 q6 0 6 5 v12 q0 7 -9 7 q-9 0 -9 -7 Z" fill={S.coin} />
    <path d="M41 40h8" stroke={S.coinDeep} strokeWidth="2.5" /><text x="23" y="42" fontSize="10" fontWeight="800" textAnchor="middle" fill={S.paper}>종합</text>
  </>,
  // 문 세 개
  gates: <>
    {[12, 28, 44].map((x, i) => <path key={x} d={`M${x} 52 V24 a6 6 0 0 1 12 0 V52`} fill="none" stroke={i === 2 ? S.coinDeep : S.sea} strokeWidth="4" />)}
  </>,
  // 저울
  debt: <>
    <path d="M32 14 V50 M22 52 h20" stroke={S.ink} strokeWidth="3" />
    <path d="M12 22 L52 30" stroke={S.ink} strokeWidth="3" />
    <rect x="8" y="23" width="14" height="10" rx="3" fill={S.no} /><rect x="44" y="31" width="12" height="7" rx="3" fill={S.sea} />
  </>,
  // 지갑
  cash: <>
    <rect x="10" y="20" width="44" height="30" rx="6" fill={S.ok} /><rect x="34" y="29" width="20" height="12" rx="4" fill="#0E8A51" />
    <circle cx="41" cy="35" r="3" fill={S.coin} /><path d="M14 20 l26 -8 l4 8" fill={S.paper} stroke={S.ok} strokeWidth="2" />
  </>,
  // 달리기 결승선
  race: <>
    <path d="M8 46 h48" stroke={S.gray} strokeWidth="3" strokeDasharray="4 3" />
    <path d="M10 44 q12 -18 22 -10 t22 -20" stroke={S.sea} strokeWidth="4" fill="none" strokeLinecap="round" />
    <path d="M10 44 q14 -8 24 -6 t20 -10" stroke={S.gray} strokeWidth="3" fill="none" strokeLinecap="round" />
    <circle cx="54" cy="14" r="5" fill={S.sea} />
  </>,
  // 점 그림
  median: <>
    {[[14, 46], [20, 46], [20, 40], [26, 46], [26, 40], [26, 34], [32, 46], [32, 40], [32, 34], [32, 28], [38, 46], [38, 40], [44, 46], [50, 46]].map(([x, y]) =>
      <circle key={`${x}-${y}`} cx={x} cy={y} r="2.6" fill={S.sea} opacity=".75" />)}
    <path d="M32 18 V50" stroke={S.deep} strokeWidth="3" /><path d="M38 18 V50" stroke={S.no} strokeWidth="2.5" strokeDasharray="3 3" />
  </>,
  // 동전 두 개
  chance: <>
    <circle cx="25" cy="34" r="13" fill={S.coin} /><circle cx="25" cy="34" r="9" fill="none" stroke={S.coinDeep} strokeWidth="2" />
    <ellipse cx="44" cy="26" rx="5" ry="12" fill={S.coinDeep} transform="rotate(25 44 26)" />
    <path d="M40 46 q6 6 12 0" stroke={S.gray} strokeWidth="2" fill="none" />
  </>,
  // 금고에서 덜어 내기
  reduction: <>
    <rect x="12" y="16" width="34" height="34" rx="5" fill={S.gray} /><circle cx="29" cy="33" r="8" fill={S.paper} /><path d="M29 27 v6 h5" stroke={S.gray} strokeWidth="2.5" fill="none" />
    <circle cx="52" cy="44" r="7" fill={S.coin} /><path d="M46 30 q8 2 6 8" stroke={S.coinDeep} strokeWidth="2.5" fill="none" />
  </>,
  // 서류와 펜
  taxpro: <>
    <rect x="14" y="10" width="30" height="40" rx="3" fill={S.paper} stroke="#7B61FF" strokeWidth="3" />
    <path d="M20 20h18M20 27h18M20 34h12" stroke="#B9A9FF" strokeWidth="2.5" />
    <path d="M40 48 L52 26 l4 2 L44 50 Z" fill="#7B61FF" />
  </>,
  // 달력과 동전
  wealth: <>
    <rect x="10" y="14" width="40" height="36" rx="5" fill={S.paper} stroke="#7B61FF" strokeWidth="3" /><rect x="10" y="14" width="40" height="10" rx="5" fill="#7B61FF" />
    <circle cx="22" cy="34" r="3" fill="#B9A9FF" /><circle cx="30" cy="34" r="3" fill="#B9A9FF" /><circle cx="38" cy="42" r="3" fill="#B9A9FF" />
    <circle cx="50" cy="48" r="8" fill={S.coin} />
  </>,
  // 의사봉
  decide: <>
    <rect x="10" y="44" width="30" height="8" rx="3" fill="#C9D6FF" />
    <rect x="22" y="14" width="22" height="12" rx="4" fill={S.deep} transform="rotate(-30 33 20)" />
    <path d="M36 26 L52 48" stroke={S.ink} strokeWidth="4" strokeLinecap="round" />
  </>,
  // 달력 위 동전
  dkinds: <>
    <rect x="10" y="14" width="44" height="38" rx="5" fill={S.paper} stroke="#E26B3A" strokeWidth="3" /><rect x="10" y="14" width="44" height="10" rx="5" fill="#E26B3A" />
    {[[18, 32], [30, 32], [42, 32], [18, 43], [30, 43], [42, 43]].map(([x, y], i) => <circle key={i} cx={x + 3} cy={y} r="4" fill={i === 5 || i === 2 ? S.coin : '#F5D2C2'} />)}
  </>,
  // 요일과 깃발
  recordday: <>
    {[10, 21, 32, 43].map((x, i) => <rect key={x} x={x} y="30" width="10" height="20" rx="3" fill={i === 3 ? '#E26B3A' : '#F5D2C2'} />)}
    <path d="M48 30 V10 l10 5 l-10 5" fill={S.coin} stroke="#E26B3A" strokeWidth="2" />
  </>,
  // 두 저울 눈금
  yieldratio: <>
    <circle cx="22" cy="32" r="14" fill="none" stroke="#E26B3A" strokeWidth="5" strokeDasharray="30 100" transform="rotate(-90 22 32)" />
    <circle cx="22" cy="32" r="14" fill="none" stroke="#F5D2C2" strokeWidth="5" strokeDasharray="58 100" strokeDashoffset="-30" transform="rotate(-90 22 32)" />
    <text x="46" y="38" fontSize="16" fontWeight="800" textAnchor="middle" fill={S.ink}>%</text>
  </>,
  // 바구니에 동전
  payback: <>
    <path d="M10 30 h44 l-5 20 h-34 Z" fill="#E26B3A" /><path d="M16 30 q16 -18 32 0" stroke="#E26B3A" strokeWidth="3" fill="none" />
    <circle cx="25" cy="27" r="5" fill={S.coin} /><circle cx="36" cy="25" r="5" fill={S.coin} /><path d="M20 38h24" stroke="#F5D2C2" strokeWidth="2" />
  </>,
  // 막대가 선을 넘음
  fincome: <>
    <rect x="12" y="34" width="10" height="16" rx="2" fill={S.gray} /><rect x="27" y="22" width="10" height="28" rx="2" fill="#C2410C" /><rect x="42" y="12" width="10" height="38" rx="2" fill="#C2410C" />
    <path d="M8 26 H56" stroke={S.no} strokeWidth="2.5" strokeDasharray="4 3" />
  </>,
  // 영수증
  withhold: <>
    <path d="M16 10 h32 v42 l-5 -4 l-5 4 l-6 -4 l-5 4 l-6 -4 l-5 4 Z" fill={S.paper} stroke="#C2410C" strokeWidth="3" />
    <path d="M22 20h20M22 27h20" stroke="#F5D2C2" strokeWidth="2.5" /><path d="M22 35h12" stroke={S.no} strokeWidth="3" />
  </>,
  // 여섯 주머니
  kinds: <>
    {[[10, 14], [26, 14], [42, 14], [10, 36], [26, 36], [42, 36]].map(([x, y], i) => <rect key={i} x={x} y={y} width="13" height="15" rx="4" fill={i < 2 ? '#C2410C' : '#F5D2C2'} />)}
  </>,
  // 계산 길 화살표
  deduct: <>
    <rect x="8" y="14" width="14" height="36" rx="3" fill="#F5D2C2" /><rect x="26" y="24" width="14" height="26" rx="3" fill="#E89A75" /><rect x="44" y="36" width="12" height="14" rx="3" fill="#C2410C" />
    <path d="M14 10 q20 -6 36 20" stroke={S.ink} strokeWidth="2" fill="none" />
  </>,
  // 더하고 빼기
  grossup: <>
    <circle cx="20" cy="32" r="12" fill={S.coin} /><text x="20" y="37" fontSize="14" fontWeight="800" textAnchor="middle" fill={S.ink}>+</text>
    <circle cx="44" cy="32" r="12" fill="#F5D2C2" /><text x="44" y="37" fontSize="16" fontWeight="800" textAnchor="middle" fill="#C2410C">−</text>
  </>,
  // 저금통
  rate: <>
    <ellipse cx="30" cy="36" rx="20" ry="14" fill="#0E9FB5" /><rect x="26" y="20" width="10" height="4" rx="2" fill={S.ink} />
    <circle cx="31" cy="12" r="6" fill={S.coin} /><circle cx="22" cy="33" r="2" fill={S.paper} /><rect x="46" y="32" width="8" height="6" rx="2" fill="#0B7F91" />
  </>,
  // 원과 달러
  fx: <>
    <circle cx="22" cy="32" r="14" fill="#0E9FB5" /><text x="22" y="38" fontSize="16" fontWeight="800" textAnchor="middle" fill={S.paper}>$</text>
    <circle cx="44" cy="32" r="12" fill={S.coin} /><text x="44" y="37" fontSize="13" fontWeight="800" textAnchor="middle" fill={S.ink}>₩</text>
    <path d="M24 12 q10 -6 20 4" stroke={S.ink} strokeWidth="2" fill="none" />
  </>,
  // 배와 가계부
  account: <>
    <path d="M8 40 h48 l-8 10 h-32 Z" fill="#0E9FB5" /><rect x="18" y="26" width="10" height="14" fill={S.coin} /><rect x="30" y="20" width="10" height="20" fill="#7FD3DF" />
    <path d="M44 16 v24" stroke={S.ink} strokeWidth="2" />
  </>,
  // 사과와 화살표
  inflation: <>
    <circle cx="26" cy="36" r="14" fill={S.no} /><path d="M26 22 q2 -8 8 -8" stroke="#0E8A51" strokeWidth="3" fill="none" />
    <path d="M44 46 L54 18 M48 20 l6 -2 l1 6" stroke="#0E9FB5" strokeWidth="3.5" fill="none" strokeLinecap="round" />
  </>,
  // 기준금리 손잡이(%)
  baserate: <>
    <circle cx="32" cy="34" r="18" fill={S.paper} stroke="#0E9FB5" strokeWidth="4" />
    <path d="M32 34 L44 22" stroke={S.ink} strokeWidth="4" strokeLinecap="round" /><circle cx="32" cy="34" r="4" fill={S.ink} />
    <text x="32" y="50" fontSize="10" fontWeight="800" textAnchor="middle" fill="#0E9FB5">%</text>
    <path d="M14 14 l4 -4 l4 4 M46 14 l4 4 l4 -4" stroke={S.coinDeep} strokeWidth="3" fill="none" strokeLinecap="round" />
  </>,
  // 장부와 막대그래프
  statements: <>
    <rect x="14" y="10" width="36" height="46" rx="4" fill={S.paper} stroke="#4C7A2E" strokeWidth="3" />
    <rect x="24" y="7" width="16" height="7" rx="2" fill="#4C7A2E" />
    <path d="M20 22h24M20 28h16" stroke={S.gray} strokeWidth="2.5" />
    <rect x="21" y="40" width="6" height="10" fill={S.sea} /><rect x="30" y="35" width="6" height="15" fill={S.coin} /><rect x="39" y="38" width="6" height="12" fill={S.ok} />
  </>,
  // 확성기
  disclosure: <>
    <path d="M12 26 h8 l20 -12 v36 l-20 -12 h-8 Z" fill="#4C7A2E" />
    <path d="M18 38 l4 12 h6 l-3 -12" fill="#4C7A2E" opacity=".7" />
    <path d="M46 24 q6 8 0 16 M51 19 q10 13 0 26" stroke={S.coinDeep} strokeWidth="3" fill="none" strokeLinecap="round" />
  </>,
  // 오르내리는 지수 선
  index: <>
    <path d="M10 10 V52 H56" stroke={S.ink} strokeWidth="3" fill="none" />
    <path d="M14 44 L24 36 L32 40 L42 24 L52 18" stroke="#D9468A" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="52" cy="18" r="4" fill={S.coin} />
  </>,
  // 멈춤 표지판
  brakes: <>
    <path d="M24 8 h16 l12 12 v16 l-12 12 h-16 l-12 -12 v-16 Z" fill={S.no} />
    <rect x="25" y="19" width="5" height="18" rx="1.5" fill={S.paper} /><rect x="34" y="19" width="5" height="18" rx="1.5" fill={S.paper} />
    <path d="M32 48 V58" stroke={S.gray} strokeWidth="4" />
  </>,
  // 녹인 선을 지나는 길
  els: <>
    <path d="M8 46 H56" stroke={S.no} strokeWidth="2.5" strokeDasharray="4 3" />
    <path d="M18 20h8M30 24h8M42 28h8" stroke={S.sea} strokeWidth="4" strokeLinecap="round" />
    <path d="M8 18 L18 30 L28 50 L38 40 L48 26 L56 22" stroke={S.ink} strokeWidth="3" fill="none" strokeLinejoin="round" />
    <circle cx="28" cy="50" r="3.5" fill={S.no} />
  </>,
  // 원금 방패와 오르는 이자
  eld: <>
    <path d="M32 8 l18 6 v14 q0 16 -18 26 q-18 -10 -18 -26 v-14 Z" fill={S.sea} />
    <circle cx="32" cy="30" r="9" fill={S.coin} stroke={S.coinDeep} strokeWidth="2" />
    <path d="M44 50 l8 -10 M47 40 h5 v5" stroke={S.ok} strokeWidth="3" fill="none" strokeLinecap="round" />
  </>,
  // 바구니와 약속 쪽지
  etn: <>
    <path d="M8 30 h24 l-3 18 h-18 Z" fill="#E8B26A" /><path d="M12 30 q8 -14 16 0" stroke="#C88A3A" strokeWidth="3" fill="none" />
    <circle cx="16" cy="28" r="3" fill={S.no} /><circle cx="23" cy="27" r="3" fill={S.ok} />
    <rect x="36" y="16" width="20" height="30" rx="2" fill={S.paper} stroke={S.ink} strokeWidth="2.5" />
    <path d="M40 24h12M40 30h12M40 36h7" stroke={S.gray} strokeWidth="2" /><circle cx="50" cy="42" r="4" fill={S.no} />
  </>,
  // 손을 든 주주들
  owners: <>
    {[14, 32, 50].map((x, i) => <g key={x}><circle cx={x} cy={i === 1 ? 24 : 28} r="6" fill={i === 1 ? S.coinDeep : S.sea} /><path d={`M${x - 8} 54 v-10 a8 8 0 0 1 16 0 v10`} fill={i === 1 ? S.coinDeep : S.sea} /></g>)}
    <path d="M58 40 V18" stroke={S.sea} strokeWidth="3.5" strokeLinecap="round" /><path d="M6 40 V20" stroke={S.sea} strokeWidth="3.5" strokeLinecap="round" />
    <path d="M28 12 l4 -5 l4 5" stroke={S.coin} strokeWidth="3" fill="none" />
  </>,
  // 다시 자른 피자
  split: <>
    <circle cx="32" cy="32" r="20" fill={S.coin} stroke="#E8B26A" strokeWidth="4" />
    {[0, 45, 90, 135].map(a => <path key={a} d="M32 12 V52" stroke={S.paper} strokeWidth="2" transform={`rotate(${a} 32 32)`} />)}
    <path d="M32 32 L32 12 A20 20 0 0 1 46 18 Z" fill="#E26B3A" />
  </>,
  // 늘고 주는 동전 탑
  capital: <>
    {[0, 1, 2, 3].map(i => <ellipse key={i} cx="22" cy={48 - i * 7} rx="12" ry="4" fill={S.coin} stroke={S.coinDeep} strokeWidth="2" />)}
    {[0, 1].map(i => <ellipse key={i} cx="46" cy={48 - i * 7} rx="10" ry="3.5" fill={S.coin} stroke={S.coinDeep} strokeWidth="2" />)}
    <path d="M22 10 v12 M16 16 h12" stroke={S.ok} strokeWidth="3.5" strokeLinecap="round" /><path d="M40 24 h12" stroke={S.no} strokeWidth="3.5" strokeLinecap="round" />
  </>,
  // 두 가게가 하나로
  mna: <>
    <circle cx="24" cy="32" r="14" fill={S.sea} opacity=".85" /><circle cx="40" cy="32" r="14" fill={S.coin} opacity=".85" />
    <path d="M10 54 h44" stroke={S.ink} strokeWidth="3" strokeLinecap="round" />
    <path d="M14 12 l6 4 l-6 4 M50 12 l-6 4 l6 4" stroke={S.ink} strokeWidth="2.5" fill="none" strokeLinecap="round" />
  </>,
  // 상장 종
  ipo: <>
    <path d="M18 44 q0 -26 14 -28 q14 2 14 28 Z" fill={S.coin} stroke={S.coinDeep} strokeWidth="2.5" />
    <rect x="14" y="44" width="36" height="5" rx="2.5" fill={S.coinDeep} /><circle cx="32" cy="53" r="4" fill={S.coinDeep} />
    <path d="M10 22 l-4 -3 M54 22 l4 -3 M8 32 h-4 M56 32 h4" stroke="#5B5F97" strokeWidth="3" strokeLinecap="round" />
  </>,
  // 내려가는 간판
  delist: <>
    <path d="M16 8 V20 M48 8 V14" stroke={S.gray} strokeWidth="3" />
    <rect x="10" y="18" width="44" height="18" rx="3" fill="#5B5F97" transform="rotate(10 32 27)" />
    <path d="M22 26 h20" stroke={S.paper} strokeWidth="3" transform="rotate(10 32 27)" />
    <path d="M32 42 V56 M26 50 l6 6 l6 -6" stroke={S.no} strokeWidth="3.5" fill="none" strokeLinecap="round" />
  </>,
  // 금 간 동전과 반창고
  distress: <>
    <circle cx="32" cy="32" r="20" fill={S.coin} stroke={S.coinDeep} strokeWidth="3" />
    <path d="M30 12 L36 24 L28 32 L36 42 L32 52" stroke={S.ink} strokeWidth="2.5" fill="none" />
    <rect x="34" y="34" width="24" height="9" rx="4" fill="#F4C9B0" transform="rotate(-30 46 38)" />
  </>,
  // 바구니에 담긴 동전과 방패
  isa: <>
    <path d="M10 28 h44 l-6 24 h-32 Z" fill="#0F766E" /><path d="M18 28 l8 -14 M46 28 l-8 -14" stroke="#0F766E" strokeWidth="3" strokeLinecap="round" />
    <circle cx="26" cy="24" r="6" fill={S.coin} /><circle cx="38" cy="22" r="6" fill={S.coinDeep} />
    <path d="M22 36 h20 M24 44 h16" stroke="#7FC8BC" strokeWidth="2.5" />
  </>,
  // 저금통과 시계
  irp: <>
    <ellipse cx="28" cy="36" rx="18" ry="14" fill="#0F766E" /><rect x="22" y="20" width="10" height="3" rx="1.5" fill={S.coinDeep} />
    <circle cx="22" cy="34" r="2" fill={S.paper} /><path d="M16 48 v4 M38 48 v4" stroke="#0F766E" strokeWidth="4" strokeLinecap="round" />
    <circle cx="48" cy="20" r="10" fill={S.paper} stroke={S.ink} strokeWidth="2.5" /><path d="M48 14 v6 h5" stroke={S.ink} strokeWidth="2.5" fill="none" />
  </>,
  // 말풍선에 금지
  whyno: <>
    <path d="M10 16 h44 v26 h-24 l-10 10 v-10 h-10 Z" fill={S.paper} stroke="#7B61FF" strokeWidth="3" />
    <circle cx="32" cy="29" r="8" fill="none" stroke={S.no} strokeWidth="3" /><path d="M26 35 L38 23" stroke={S.no} strokeWidth="3" />
  </>,
  // 은행 금고와 동전 쌓기
  deposit: <>
    <path d="M10 24 L32 12 L54 24 Z" fill="#2563EB" /><rect x="14" y="24" width="36" height="4" fill="#2563EB" />
    <path d="M18 30 v16 M28 30 v16 M36 30 v16 M46 30 v16" stroke="#2563EB" strokeWidth="4" /><rect x="12" y="46" width="40" height="5" rx="1" fill="#2563EB" />
    <circle cx="50" cy="50" r="7" fill={S.coin} stroke={S.coinDeep} strokeWidth="2" />
  </>,
  // 주차장 표지와 방패
  cmaima: <>
    <rect x="10" y="12" width="26" height="26" rx="5" fill="#2563EB" /><path d="M19 32 V18 h6 a5 5 0 0 1 0 10 h-6" stroke={S.paper} strokeWidth="3.5" fill="none" strokeLinejoin="round" />
    <path d="M44 24 l10 4 v8 c0 8 -5 13 -10 15 c-5 -2 -10 -7 -10 -15 v-8 Z" fill={S.coin} stroke={S.coinDeep} strokeWidth="2" />
    <path d="M39 37 l4 4 7 -8" stroke={S.ink} strokeWidth="2.5" fill="none" strokeLinecap="round" />
  </>,
}

export function ColumnIcon({ id, size = 64 }: { id: string; size?: number }) {
  return <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">{ICONS[id]}</svg>
}
