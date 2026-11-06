// 웹 화면(app/web/src)의 글·모형 자료를 그대로 뽑아 app/web_text.json으로 쓴다.
// Streamlit 화면은 이 파일만 읽으므로 문구를 손으로 옮겨 적지 않는다. 웹 문구가 바뀌면 다시 실행한다.
//   node app/export_web_text.mjs   (esbuild는 app/web/node_modules에서 찾는다)
import { createRequire } from 'node:module'
import { existsSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
// 워크트리에는 node_modules가 없을 수 있어, 저장소 메인 폴더의 app/web/node_modules도 찾아본다
const candidates = [join(root, 'app', 'web'), resolve(root, '../../../app/web')]  // 메인 폴더 또는 워크트리
const webDir = candidates.find(d => existsSync(join(d, 'node_modules', 'esbuild')))
if (!webDir) throw new Error('app/web/node_modules/esbuild가 없어요. cd app/web && npm install 뒤 다시 실행해 주세요.')
const esbuild = createRequire(join(webDir, 'package.json'))('esbuild')

const entry = `
export * as bank from './bank'
export * as legal from './legal'
export * as column from './column'
`
const tmp = mkdtempSync(join(tmpdir(), 'onepick-text-'))
const out = join(tmp, 'text.mjs')
await esbuild.build({
  stdin: { contents: entry, resolveDir: join(root, 'app', 'web', 'src'), loader: 'ts' },
  bundle: true, format: 'esm', platform: 'node', outfile: out, logLevel: 'error',
})
const m = await import(pathToFileURL(out).href)
rmSync(tmp, { recursive: true, force: true })

const pick = (mod, keys) => Object.fromEntries(keys.map(k => [k, mod[k]]))
const text = {
  bank: pick(m.bank, ['BANK', 'SAVED_NOTE', 'MOCK_NOTE', 'BRANCHES', 'REGIONS', 'CONSULT_TYPES', 'WAYS', 'SLOTS']),
  legal: pick(m.legal, ['LEGAL_MOCK', 'PRIVACY', 'TERMS', 'JUDGE_YEAR']),
  column: {
    ...pick(m.column, ['COLUMN_NOTE', 'UNITS', 'GLOSSARY', 'THEMES', 'START_HERE', 'READ_ORDER', 'EPISODES']),
    // column.ts의 나머지 상수(함수 제외)도 함께 둔다
    ...Object.fromEntries(Object.entries(m.column).filter(([, v]) => typeof v !== 'function')),
  },
}
writeFileSync(join(here, 'web_text.json'), JSON.stringify(text, null, 1) + '\n')
console.log('web_text.json:', Object.entries(text).map(([k, v]) => `${k} ${Object.keys(v).length}개`).join(' · '))

// 법 토너먼트 그림(app/web/src/components/tournamentEngine.ts)을 브라우저용 한 파일로 묶는다.
// 화면 코드는 그대로 쓰고, 모아 그림 주소(moaSrc)만 Streamlit이 넣어 주는 data URL(window.ONEPICK_MOA)로 바꾼다.
const utilShim = {
  name: 'moa-src',
  setup(b) {
    b.onResolve({ filter: /^\.\.\/util$/ }, () => ({ path: 'util-shim', namespace: 'shim' }))
    b.onLoad({ filter: /.*/, namespace: 'shim' }, () => ({ contents: 'export const moaSrc = m => (window.ONEPICK_MOA || {})[m] || ""', loader: 'js' }))
  },
}
await esbuild.build({
  entryPoints: [join(root, 'app', 'web', 'src', 'components', 'tournamentEngine.ts')],
  bundle: true, format: 'iife', globalName: 'OnePickTournament', platform: 'browser', minify: true,
  outfile: join(here, 'web_tournament.js'), plugins: [utilShim], logLevel: 'error',
})
console.log('web_tournament.js: 법 토너먼트 그림')
