// 금융 상식 칼럼(app/web/src/pages/Column.tsx)의 그림을 Streamlit에서 그대로 쓰려고 뽑는다.
//   column_icons.json   : 글마다 붙는 그림 기호(columnIcons.tsx)를 SVG 글로
//   web_column_toys.js  : 그림 도구(columnToys.tsx)를 브라우저에서 바로 그리는 한 파일
//                         (API 값을 쓰는 세율 계단·달리기 시합·점 찍어 보기는 Streamlit이 api 함수로 따로 그린다)
//   node app/export_column_assets.mjs   (esbuild·react는 app/web/node_modules에서 찾는다)
import { createRequire } from 'node:module'
import { existsSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const candidates = [join(root, 'app', 'web'), resolve(root, '../../../app/web')]  // 메인 폴더 또는 워크트리
const webDir = candidates.find(d => existsSync(join(d, 'node_modules', 'esbuild')))
if (!webDir) throw new Error('app/web/node_modules/esbuild가 없어요. cd app/web && npm install 뒤 다시 실행해 주세요.')
const esbuild = createRequire(join(webDir, 'package.json'))('esbuild')
const nodePaths = [join(webDir, 'node_modules')]
const src = join(root, 'app', 'web', 'src')

// 1) 그림 기호: 서버 쪽 React로 SVG 글을 만든다
const tmp = mkdtempSync(join(tmpdir(), 'onepick-col-'))
const out = join(tmp, 'icons.cjs')
await esbuild.build({
  stdin: {
    contents: `import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ColumnIcon } from './components/columnIcons'
import { EPISODES } from './column'
export const icons = Object.fromEntries(EPISODES.map(e => [e.id, renderToStaticMarkup(createElement(ColumnIcon, { id: e.id, size: 64 }))]))`,
    resolveDir: src, loader: 'tsx',
  },
  bundle: true, format: 'cjs', platform: 'node', outfile: out, nodePaths, jsx: 'automatic', logLevel: 'error',
})
const { icons } = createRequire(import.meta.url)(out)
rmSync(tmp, { recursive: true, force: true })
writeFileSync(join(here, 'column_icons.json'), JSON.stringify(icons, null, 1) + '\n')
console.log(`column_icons.json: 그림 기호 ${Object.keys(icons).length}개`)

// 2) 그림 도구: 이름으로 골라 화면에 붙이는 mount(el, name)
await esbuild.build({
  stdin: {
    contents: `import { createElement } from 'react'
import { createRoot } from 'react-dom/client'
import * as T from './components/columnToys'
export function mount(el, name) { const C = T[name]; if (!C) return; createRoot(el).render(createElement(C)) }`,
    resolveDir: src, loader: 'tsx',
  },
  bundle: true, format: 'iife', globalName: 'OnePickToys', platform: 'browser', minify: true, nodePaths, jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' }, outfile: join(here, 'web_column_toys.js'), logLevel: 'error',
})
console.log('web_column_toys.js: 그림 도구')
