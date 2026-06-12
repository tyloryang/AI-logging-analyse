#!/usr/bin/env node
/**
 * AIOPS Code — Claude Code 风格的 AI 运维智能体 CLI
 *
 * 用法:
 *   node dist/index.mjs [chat|rca|inspect|guided]        交互模式
 *   node dist/index.mjs -p "查询最近错误日志"              一次性 print 模式（可脚本化）
 *   AIOPS_URL=http://host:8000 node dist/index.mjs       指定后端地址
 *   AIOPS_USER=xxx AIOPS_PASS=yyy node dist/index.mjs    免交互登录
 *
 * 会话凭据缓存在 ~/.aiops-code.json，登录一次后续免登录。
 */
import React, {
  useState, useEffect, useReducer, useCallback,
} from 'react'
import {
  render, Box, Text, useInput, useApp, Static,
} from 'ink'
import TextInput from 'ink-text-input'
import { randomUUID } from 'crypto'
import { readFileSync, writeFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

// ─── 配置与凭据 ────────────────────────────────────────────────────────────────
const CONFIG_PATH = join(homedir(), '.aiops-code.json')

function loadConfig() {
  try { return JSON.parse(readFileSync(CONFIG_PATH, 'utf-8')) } catch { return {} }
}
function saveConfig(patch) {
  const cfg = { ...loadConfig(), ...patch }
  try { writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2)) } catch {}
  return cfg
}

const CFG   = loadConfig()
const BASE  = process.env.AIOPS_URL || CFG.baseUrl || 'http://127.0.0.1:8000'
const MODES = ['chat', 'rca', 'inspect', 'guided']
const META  = {
  chat:    { label: 'chat',    badge: 'cyan',    desc: 'General assistant'      },
  rca:     { label: 'rca',     badge: 'yellow',  desc: 'Root cause analysis'    },
  inspect: { label: 'inspect', badge: 'green',   desc: 'System inspection'      },
  guided:  { label: 'guided',  badge: 'magenta', desc: 'Guided troubleshooting' },
}
const W = Math.max(80, Math.min(process.stdout.columns ?? 100, 200))
const SPIN_FRAMES = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']

// ─── HTTP 封装（带 session cookie）────────────────────────────────────────────
let SESSION_ID = process.env.AIOPS_SESSION || CFG.sessionId || ''

function authHeaders(extra = {}) {
  const h = { 'Content-Type': 'application/json', ...extra }
  if (SESSION_ID) h.Cookie = `session_id=${SESSION_ID}`
  return h
}

function extractSessionId(res) {
  let cookies = []
  if (typeof res.headers.getSetCookie === 'function') cookies = res.headers.getSetCookie()
  else { const c = res.headers.get('set-cookie'); if (c) cookies = [c] }
  for (const c of cookies) {
    const m = /session_id=([^;]+)/.exec(c)
    if (m) return m[1]
  }
  return ''
}

async function apiLogin(username, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail ?? detail } catch {}
    throw new Error(detail)
  }
  const sid = extractSessionId(res)
  if (!sid) throw new Error('登录成功但未返回 session cookie')
  SESSION_ID = sid
  const me = await res.json()
  saveConfig({ baseUrl: BASE, sessionId: sid, username: me.username })
  return me
}

async function apiMe() {
  if (!SESSION_ID) return null
  try {
    const res = await fetch(`${BASE}/api/auth/me`, { headers: authHeaders() })
    if (!res.ok) return null
    return await res.json()
  } catch { return null }
}

async function apiHealth() {
  const res = await fetch(`${BASE}/api/health`, { headers: authHeaders() })
  return res.json()
}

async function apiSaveConversation(convId, mode, title, messages) {
  try {
    await fetch(`${BASE}/api/agent/conversations/${convId}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({ mode, title, messages }),
    })
  } catch {}
}

// ─── SSE 流式对话 ──────────────────────────────────────────────────────────────
async function streamAgent(mode, message, convId, handlers) {
  const res = await fetch(`${BASE}/api/agent/${mode}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message, conv_id: convId }),
  })
  if (res.status === 401) throw new Error('AUTH_REQUIRED')
  if (!res.ok) {
    let d = `HTTP ${res.status}`
    try { d = (await res.json()).detail ?? d } catch {}
    throw new Error(d)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      let e
      try { e = JSON.parse(line.slice(6)) } catch { continue }
      handlers[e.type]?.(e)
    }
  }
}

// ─── print 模式（claude -p 风格，无 TTY 也可用）──────────────────────────────
async function runPrintMode(mode, message) {
  // 1) 已存 session 可用则直接用；否则尝试环境变量登录
  let me = await apiMe()
  if (!me) {
    const user = process.env.AIOPS_USER || ''
    const pass = process.env.AIOPS_PASS || ''
    if (!user || !pass) {
      console.error('未登录。请设置 AIOPS_USER / AIOPS_PASS 环境变量，或先运行交互模式登录一次。')
      process.exit(2)
    }
    try { me = await apiLogin(user, pass) } catch (e) {
      console.error(`登录失败: ${e.message}`)
      process.exit(2)
    }
  }
  const convId = randomUUID()
  let hadError = false
  try {
    await streamAgent(mode, message, convId, {
      token:           e => process.stdout.write(e.text ?? ''),
      tool_start:      e => process.stderr.write(`\n⎿  ${e.tool} …\n`),
      tool_end:        () => {},
      replace_content: () => {},
      error:           e => { hadError = true; process.stderr.write(`\n✖ ${e.message}\n`) },
      done:            () => process.stdout.write('\n'),
    })
  } catch (e) {
    console.error(`✖ ${e.message === 'AUTH_REQUIRED' ? '会话已过期，请重新登录' : e.message}`)
    process.exit(1)
  }
  process.exit(hadError ? 1 : 0)
}

// ─── 交互模式状态机 ────────────────────────────────────────────────────────────
const INIT = {
  hist:    [],
  stream:  null,     // { text, tools[], cur }
  input:   '',
  mode:    'chat',
  busy:    false,
  err:     '',
  notice:  '',
  convId:  randomUUID(),
  frame:   0,
  epoch:   0,
}

function reducer(s, a) {
  switch (a.type) {
    case 'INPUT':   return { ...s, input: a.v }
    case 'MODE':    return { ...s, mode: a.v, notice: `模式已切换 → ${a.v}` }
    case 'TICK':    return { ...s, frame: (s.frame + 1) % SPIN_FRAMES.length }
    case 'RESET':   return { ...INIT, mode: s.mode, convId: randomUUID(), epoch: s.epoch + 1,
                             notice: '已开启新会话' }
    case 'CLEAR':   return { ...s, hist: [], epoch: s.epoch + 1 }
    case 'ERR':     return { ...s, busy: false, stream: null, err: a.v }
    case 'CLR_ERR': return { ...s, err: '', notice: '' }
    case 'NOTICE':  return { ...s, notice: a.v }

    case 'SEND': {
      const msg = { id: randomUUID(), role: 'human', text: a.text, tools: [] }
      return { ...s, hist: [...s.hist, msg], input: '', busy: true, err: '', notice: '',
               stream: { text: '', tools: [], cur: null } }
    }
    case 'TOKEN':
      if (!s.stream) return s
      return { ...s, busy: false, stream: { ...s.stream, text: s.stream.text + a.v } }
    case 'TOOL_START':
      if (!s.stream) return s
      return { ...s, busy: false,
               stream: { ...s.stream, cur: { name: a.name, inp: a.inp, ts: Date.now() } } }
    case 'TOOL_END': {
      if (!s.stream) return s
      const dur  = s.stream.cur ? Date.now() - s.stream.cur.ts : 0
      const tool = { name: a.name, inp: s.stream.cur?.inp, out: a.out, dur }
      return { ...s, stream: { ...s.stream, tools: [...s.stream.tools, tool], cur: null } }
    }
    case 'REPLACE':
      if (!s.stream) return s
      return { ...s, stream: { ...s.stream, text: a.v } }
    case 'DONE': {
      if (!s.stream) return { ...s, busy: false }
      const msg = { id: randomUUID(), role: 'assistant',
                    text: s.stream.text, tools: s.stream.tools }
      return { ...s, hist: [...s.hist, msg], stream: null, busy: false }
    }
    default: return s
  }
}

// ─── slash 命令 ────────────────────────────────────────────────────────────────
const SLASH_HELP = [
  ['/help',          '显示本帮助'],
  ['/mode <m>',      `切换模式 (${MODES.join('/')})，等价 Tab`],
  ['/status',        '查看后端健康状态（Loki/Prometheus/AI）'],
  ['/reset',         '开启新会话（清空上下文），等价 Ctrl+R'],
  ['/clear',         '清屏（保留上下文），等价 Ctrl+L'],
  ['/logout',        '退出登录并清除本地凭据'],
  ['/exit',          '退出 CLI'],
]

// ─── UI 组件 ───────────────────────────────────────────────────────────────────
function truncate(v, max) {
  if (v == null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

function Multiline({ text, color, dimmed }) {
  const lines = String(text ?? '').split('\n')
  return (
    <>
      {lines.map((l, i) => (
        <Box key={i}>
          <Text color={color} dimColor={dimmed} wrap="wrap">{l === '' ? ' ' : l}</Text>
        </Box>
      ))}
    </>
  )
}

function ToolRow({ t, active, spinChar }) {
  const inp = truncate(t.inp, 60)
  const out = truncate(t.out, 120)
  return (
    <Box flexDirection="column">
      <Box>
        <Text color={active ? '#e5c07b' : '#5c6370'}>{'  ⎿  '}</Text>
        <Text color={active ? '#e5c07b' : '#abb2bf'} bold={active}>{t.name}</Text>
        {inp ? <Text color="#4b5263">{'(' + inp + ')'}</Text> : null}
        {active
          ? <Text color="#e5c07b">  {spinChar}</Text>
          : (
            <Box marginLeft={1}>
              <Text color="#98c379">{'✓'}</Text>
              {t.dur != null ? <Text color="#4b5263">{' ' + t.dur + 'ms'}</Text> : null}
            </Box>
          )}
      </Box>
      {!active && out && (
        <Box paddingLeft={7}>
          <Text color="#4b5263" wrap="wrap">{out}</Text>
        </Box>
      )}
    </Box>
  )
}

function HistMsg({ m }) {
  if (m.role === 'human') {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Box>
          <Text color="#7f848e" bold>Human: </Text>
          <Text wrap="wrap">{m.text}</Text>
        </Box>
      </Box>
    )
  }
  if (m.role === 'system') {
    return (
      <Box flexDirection="column" marginBottom={1} paddingLeft={2}>
        <Multiline text={m.text} color="#5c6370" />
      </Box>
    )
  }
  return (
    <Box flexDirection="column" marginBottom={1}>
      {m.tools?.map((t, i) => <ToolRow key={i} t={t} active={false} spinChar="" />)}
      {m.text ? <Box><Box flexDirection="column"><Multiline text={m.text} /></Box></Box> : null}
    </Box>
  )
}

function LiveMsg({ stream, busy, spinChar }) {
  if (!stream && !busy) return null
  return (
    <Box flexDirection="column" marginBottom={1}>
      {busy && !stream?.text && !stream?.tools?.length && !stream?.cur && (
        <Box>
          <Text color="#528bff">{spinChar}</Text>
          <Text color="#4b5263" italic>  Thinking…</Text>
        </Box>
      )}
      {stream && (
        <>
          {stream.tools.map((t, i) => <ToolRow key={i} t={t} active={false} spinChar="" />)}
          {stream.cur && <ToolRow t={stream.cur} active spinChar={spinChar} />}
          {stream.text && (
            <Box flexDirection="column">
              <Multiline text={stream.text} />
              <Box><Text color="#528bff">{spinChar}</Text></Box>
            </Box>
          )}
        </>
      )}
    </Box>
  )
}

function Header({ mode, busy, spinChar, username }) {
  const m = META[mode] ?? META.chat
  return (
    <Box justifyContent="space-between" paddingX={1}>
      <Box gap={1}>
        <Text color="#528bff" bold>◆</Text>
        <Text bold>AIOPS Code</Text>
        <Text color="#4b5263">·</Text>
        <Text color="#5c6370">AI 运维智能体</Text>
        {username ? (
          <>
            <Text color="#4b5263">·</Text>
            <Text color="#98c379">{username}</Text>
          </>
        ) : null}
        {busy && (
          <>
            <Text color="#4b5263">·</Text>
            <Text color="#5c6370" italic>thinking {spinChar}</Text>
          </>
        )}
      </Box>
      <Box gap={1}>
        <Text color={m.badge} bold>{m.label}</Text>
        <Text color="#4b5263" italic>{m.desc}</Text>
      </Box>
    </Box>
  )
}

function HR({ bright }) {
  return (
    <Box>
      <Text color={bright ? '#3e4451' : '#21252b'}>{'─'.repeat(W)}</Text>
    </Box>
  )
}

function Footer({ mode }) {
  return (
    <Box paddingX={1} gap={3} marginTop={0}>
      <Box gap={1}>
        {MODES.map((m, i) => {
          const active = m === mode
          const color  = active ? META[m].badge : '#3e4451'
          return (
            <Box key={m}>
              {i > 0 && <Text color="#21252b"> </Text>}
              <Text color={color} bold={active}>
                {active ? `[${META[m].label}]` : META[m].label}
              </Text>
            </Box>
          )
        })}
      </Box>
      <Text color="#3e4451">tab 切换</Text>
      <Text color="#3e4451">/help 命令</Text>
      <Text color="#3e4451">ctrl+c 退出</Text>
    </Box>
  )
}

function ErrBanner({ msg }) {
  if (!msg) return null
  return (
    <Box paddingX={2} marginBottom={1}>
      <Text color="#e06c75">✖  </Text>
      <Text color="#e06c75" wrap="wrap">{msg}</Text>
      <Text color="#4b5263">  (esc)</Text>
    </Box>
  )
}

function NoticeBanner({ msg }) {
  if (!msg) return null
  return (
    <Box paddingX={2} marginBottom={1}>
      <Text color="#98c379">✓  </Text>
      <Text color="#5c6370" wrap="wrap">{msg}</Text>
    </Box>
  )
}

function Welcome({ base }) {
  return (
    <Box flexDirection="column" paddingX={1} marginBottom={1}>
      <Text color="#5c6370">
        {'  ✻ '}
        <Text color="#abb2bf">Welcome to </Text>
        <Text color="#528bff" bold>AIOPS Code</Text>
        <Text color="#abb2bf">, your intelligent operations assistant.</Text>
      </Text>
      <Text color="#4b5263">
        {'    backend: '}
        <Text color="#5c6370">{base}</Text>
      </Text>
      <Text color="#4b5263">
        {'    Use '}
        <Text color="#e5c07b">natural language</Text>
        {' to query logs, inspect hosts, analyze errors. Type '}
        <Text color="#e5c07b">/help</Text>
        {' for commands.'}
      </Text>
    </Box>
  )
}

// ─── 登录向导 ──────────────────────────────────────────────────────────────────
function LoginWizard({ onDone }) {
  const [step, setStep]   = useState('user')   // user | pass | busy
  const [user, setUser]   = useState(process.env.AIOPS_USER || loadConfig().username || '')
  const [pass, setPass]   = useState('')
  const [err,  setErr]    = useState('')

  const submit = useCallback(async () => {
    if (step === 'user') {
      if (!user.trim()) return
      setStep('pass')
      return
    }
    if (step === 'pass') {
      if (!pass) return
      setStep('busy')
      try {
        const me = await apiLogin(user.trim(), pass)
        onDone(me)
      } catch (e) {
        setErr(String(e.message))
        setPass('')
        setStep('pass')
      }
    }
  }, [step, user, pass, onDone])

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text color="#528bff" bold>◆ AIOPS Code </Text>
        <Text color="#5c6370">登录到 {BASE}</Text>
      </Box>
      {err ? (
        <Box marginBottom={1}>
          <Text color="#e06c75">✖ {err}</Text>
        </Box>
      ) : null}
      {step === 'user' && (
        <Box>
          <Text color="#abb2bf">用户名: </Text>
          <TextInput value={user} onChange={setUser} onSubmit={submit} />
        </Box>
      )}
      {step === 'pass' && (
        <Box flexDirection="column">
          <Box><Text color="#4b5263">用户名: {user}</Text></Box>
          <Box>
            <Text color="#abb2bf">密  码: </Text>
            <TextInput value={pass} onChange={setPass} onSubmit={submit} mask="*" />
          </Box>
        </Box>
      )}
      {step === 'busy' && (
        <Box><Text color="#5c6370" italic>正在登录…</Text></Box>
      )}
    </Box>
  )
}

// ─── 主程序 ────────────────────────────────────────────────────────────────────
function App({ initialMode, initialUser }) {
  const { exit }      = useApp()
  const [s, dispatch] = useReducer(reducer, { ...INIT, mode: initialMode })
  const [me, setMe]   = useState(initialUser)   // null = 需要登录

  // spinner
  useEffect(() => {
    if (!s.busy && !s.stream) return
    const id = setInterval(() => dispatch({ type: 'TICK' }), 80)
    return () => clearInterval(id)
  }, [s.busy, !!s.stream])

  // 会话自动保存：assistant 消息落地后同步到服务端（与 Web 端历史互通）
  useEffect(() => {
    if (!me || !s.hist.length) return
    const last = s.hist[s.hist.length - 1]
    if (last.role !== 'assistant') return
    const firstHuman = s.hist.find(m => m.role === 'human')
    const title = `[CLI] ${truncate(firstHuman?.text ?? '新会话', 40)}`
    const messages = s.hist
      .filter(m => m.role !== 'system')
      .map(m => ({
        role: m.role === 'human' ? 'user' : 'assistant',
        content: m.text,
        tools: (m.tools ?? []).map(t => ({ name: t.name, input: t.inp ?? '', output: t.out ?? '' })),
      }))
    apiSaveConversation(s.convId, s.mode, title, messages)
  }, [s.hist.length, me])

  const runMessage = useCallback((text) => {
    dispatch({ type: 'SEND', text })
    streamAgent(s.mode, text, s.convId, {
      token:           e => dispatch({ type: 'TOKEN', v: e.text }),
      tool_start:      e => dispatch({ type: 'TOOL_START', name: e.tool, inp: e.input }),
      tool_end:        e => dispatch({ type: 'TOOL_END', name: e.tool, out: e.output }),
      replace_content: e => dispatch({ type: 'REPLACE', v: e.text }),
      error:           e => dispatch({ type: 'ERR', v: e.message }),
      done:            () => dispatch({ type: 'DONE' }),
    }).then(() => dispatch({ type: 'DONE' }))
      .catch(e => {
        if (e.message === 'AUTH_REQUIRED') {
          saveConfig({ sessionId: '' }); SESSION_ID = ''
          setMe(null)
          dispatch({ type: 'ERR', v: '会话已过期，请重新登录' })
        } else {
          dispatch({ type: 'ERR', v: `连接失败: ${e.message}` })
        }
      })
  }, [s.mode, s.convId])

  const handleSlash = useCallback(async (cmd) => {
    const [name, ...rest] = cmd.slice(1).split(/\s+/)
    const arg = rest.join(' ')
    dispatch({ type: 'INPUT', v: '' })
    switch (name) {
      case 'help': {
        const text = SLASH_HELP.map(([c, d]) => `${c.padEnd(14)} ${d}`).join('\n')
        dispatch({ type: 'NOTICE', v: '可用命令：\n' + text })
        return
      }
      case 'mode': {
        if (MODES.includes(arg)) dispatch({ type: 'MODE', v: arg })
        else dispatch({ type: 'ERR', v: `未知模式 "${arg}"，可用: ${MODES.join(' / ')}` })
        return
      }
      case 'status': {
        try {
          const h = await apiHealth()
          dispatch({ type: 'NOTICE', v:
            `backend: ${BASE}\n` +
            `loki: ${h.loki_connected ? '✓' : '✗'} ${h.loki_url ?? ''}\n` +
            `prometheus: ${h.prometheus_connected ? '✓' : '✗'} ${h.prometheus_url ?? ''}\n` +
            `ai: ${h.ai_ready ? '✓' : '✗'} ${h.ai_provider ?? ''}` })
        } catch (e) {
          dispatch({ type: 'ERR', v: `后端不可达: ${e.message}` })
        }
        return
      }
      case 'reset':  dispatch({ type: 'RESET' });  return
      case 'clear':  dispatch({ type: 'CLEAR' });  return
      case 'logout':
        saveConfig({ sessionId: '' }); SESSION_ID = ''
        setMe(null)
        return
      case 'exit': case 'quit': exit(); return
      default:
        dispatch({ type: 'ERR', v: `未知命令 ${cmd}，输入 /help 查看可用命令` })
    }
  }, [exit])

  const send = useCallback(() => {
    const text = s.input.trim()
    if (!text || s.busy) return
    if (text.startsWith('/')) { handleSlash(text); return }
    runMessage(text)
  }, [s.input, s.busy, handleSlash, runMessage])

  useInput((ch, key) => {
    if (!me) return
    if (key.ctrl) {
      if (ch === 'c') { exit(); return }
      if (ch === 'r') { dispatch({ type: 'RESET' }); return }
      if (ch === 'l') { dispatch({ type: 'CLEAR' }); return }
    }
    if (key.tab)    { const i = MODES.indexOf(s.mode); dispatch({ type: 'MODE', v: MODES[(i+1)%MODES.length] }); return }
    if (key.escape) { dispatch({ type: 'CLR_ERR' }); return }
  })

  if (!me) {
    return <LoginWizard onDone={u => { setMe(u); dispatch({ type: 'NOTICE', v: `已登录: ${u.username}` }) }} />
  }

  const spinChar = SPIN_FRAMES[s.frame]
  const empty    = s.hist.length === 0 && !s.stream && !s.busy

  return (
    <Box flexDirection="column" width={W}>
      <Header mode={s.mode} busy={s.busy} spinChar={spinChar} username={me.username} />
      <HR bright />
      <Box height={1} />
      {empty && <Welcome base={BASE} />}
      <Static items={s.hist} key={s.epoch}>
        {m => <HistMsg key={m.id} m={m} />}
      </Static>
      <LiveMsg stream={s.stream} busy={s.busy} spinChar={spinChar} />
      <ErrBanner msg={s.err} />
      <NoticeBanner msg={s.notice} />
      <HR />
      <Box paddingX={1}>
        <Text color={s.busy ? '#3e4451' : '#528bff'} bold>{'> '}</Text>
        <TextInput
          value={s.input}
          onChange={v => dispatch({ type: 'INPUT', v })}
          onSubmit={send}
          placeholder={s.busy ? '' : 'Send a message… (/help)'}
          focus={!s.busy}
        />
      </Box>
      <HR />
      <Footer mode={s.mode} />
      <Box height={1} />
    </Box>
  )
}

// ─── 入口 ──────────────────────────────────────────────────────────────────────
async function main() {
  const argv = process.argv.slice(2)

  // print 模式: -p / --print "消息"
  const pIdx = argv.findIndex(a => a === '-p' || a === '--print')
  if (pIdx !== -1) {
    const modeArg = argv.find(a => MODES.includes(a)) ?? 'chat'
    const message = argv.filter((a, i) => i !== pIdx && !MODES.includes(a)).join(' ').trim()
    if (!message) {
      console.error('用法: aiops -p "你的问题" [chat|rca|inspect|guided]')
      process.exit(2)
    }
    await runPrintMode(modeArg, message)
    return
  }

  if (!process.stdin.isTTY) {
    console.error('交互模式需要 TTY 终端。脚本调用请使用: aiops -p "你的问题"')
    process.exit(1)
  }

  const initialMode = MODES.includes(argv[0]) ? argv[0] : 'chat'

  // 启动时检查已存会话；环境变量可免交互登录
  let me = await apiMe()
  if (!me && process.env.AIOPS_USER && process.env.AIOPS_PASS) {
    try { me = await apiLogin(process.env.AIOPS_USER, process.env.AIOPS_PASS) } catch {}
  }

  render(<App initialMode={initialMode} initialUser={me} />, { patchConsole: false })
}

main()
