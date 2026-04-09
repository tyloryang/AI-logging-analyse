#!/usr/bin/env node
/**
 * AI 运维智能体 CLI — 高度还原 Claude Code 界面风格
 *
 * 用法:
 *   node dist/index.mjs [chat|rca|inspect|guided]
 *   AIOPS_URL=http://host:port node dist/index.mjs
 */
import React, {
  useState, useEffect, useReducer, useCallback, useRef,
} from 'react'
import {
  render, Box, Text, useInput, useApp, Static, Newline,
} from 'ink'
import TextInput from 'ink-text-input'
import { randomUUID } from 'crypto'

// ─── 配置 ──────────────────────────────────────────────────────────────────────
const BASE  = process.env.AIOPS_URL || 'http://192.168.9.221:30800'
const MODES = ['chat', 'rca', 'inspect', 'guided']
const META  = {
  chat:    { label: 'chat',    badge: 'cyan',    desc: 'General assistant'         },
  rca:     { label: 'rca',     badge: 'yellow',  desc: 'Root cause analysis'       },
  inspect: { label: 'inspect', badge: 'green',   desc: 'System inspection'         },
  guided:  { label: 'guided',  badge: 'magenta', desc: 'Guided troubleshooting'    },
}
const IMODE = MODES.includes(process.argv[2]) ? process.argv[2] : 'chat'
const W     = Math.max(80, Math.min(process.stdout.columns ?? 100, 200))

// 旋转帧 — 仿 Claude Code 右上角"thinking"动画
const SPIN_FRAMES = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']

// ─── 状态 ──────────────────────────────────────────────────────────────────────
const INIT = {
  hist:     [],       // 已完成消息 → Static
  stream:   null,     // { text, tools[], cur }
  input:    '',
  mode:     IMODE,
  busy:     false,
  err:      '',
  convId:   randomUUID(),
  frame:    0,
  epoch:    0,        // Ctrl+L 清屏计数
}

function reducer(s, a) {
  switch (a.type) {
    case 'INPUT':  return { ...s, input: a.v }
    case 'MODE':   return { ...s, mode: a.v }
    case 'TICK':   return { ...s, frame: (s.frame + 1) % SPIN_FRAMES.length }
    case 'RESET':  return { ...INIT, mode: s.mode, convId: randomUUID() }
    case 'CLEAR':  return { ...s, hist: [], epoch: s.epoch + 1 }
    case 'ERR':    return { ...s, busy: false, stream: null, err: a.v }
    case 'CLR_ERR':return { ...s, err: '' }

    case 'SEND': {
      const msg = { id: randomUUID(), role: 'human', text: s.input.trim(), tools: [] }
      return { ...s, hist: [...s.hist, msg], input: '', busy: true, err: '',
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

// ─── 网络 ──────────────────────────────────────────────────────────────────────
async function callAgent(mode, message, convId, dispatch) {
  try {
    const res = await fetch(`${BASE}/api/agent/${mode}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message, conv_id: convId }),
    })
    if (!res.ok) {
      let d = `HTTP ${res.status}`
      try { d = (await res.json()).detail ?? d } catch {}
      return dispatch({ type: 'ERR', v: d })
    }
    const reader = res.body.getReader()
    const dec    = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const e = JSON.parse(line.slice(6))
          if      (e.type === 'token')           dispatch({ type: 'TOKEN', v: e.text })
          else if (e.type === 'tool_start')      dispatch({ type: 'TOOL_START', name: e.tool, inp: e.input })
          else if (e.type === 'tool_end')        dispatch({ type: 'TOOL_END',   name: e.tool, out: e.output })
          else if (e.type === 'replace_content') dispatch({ type: 'REPLACE',    v: e.text })
          else if (e.type === 'done')            dispatch({ type: 'DONE' })
          else if (e.type === 'error')           dispatch({ type: 'ERR', v: e.message })
        } catch {}
      }
    }
    dispatch({ type: 'DONE' })
  } catch (e) {
    dispatch({ type: 'ERR', v: `连接失败: ${e.message}` })
  }
}

// ─── 辅助 ──────────────────────────────────────────────────────────────────────
function truncate(v, max) {
  if (v == null) return ''
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

// 多行文本（支持 \n）
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

// ─── 工具调用行 ────────────────────────────────────────────────────────────────
//
// Claude Code 原版风格:
//   ⎿  ToolName(input_preview)                         ✓ 42ms
//      result preview...
//
function ToolRow({ t, active, spinChar }) {
  const inp = truncate(t.inp, 60)
  const out = truncate(t.out, 120)
  return (
    <Box flexDirection="column">
      {/* 工具名行 */}
      <Box>
        <Text color={active ? '#e5c07b' : '#5c6370'}>{'  ⎿  '}</Text>
        <Text color={active ? '#e5c07b' : '#abb2bf'} bold={active}>
          {t.name}
        </Text>
        {inp
          ? <Text color="#4b5263">{'(' + inp + ')'}</Text>
          : null
        }
        {active
          ? <Text color="#e5c07b">  {spinChar}</Text>
          : (
            <Box marginLeft={1}>
              <Text color="#98c379">{'✓'}</Text>
              {t.dur != null
                ? <Text color="#4b5263">{' ' + t.dur + 'ms'}</Text>
                : null
              }
            </Box>
          )
        }
      </Box>
      {/* 返回值行 */}
      {!active && out && (
        <Box paddingLeft={7}>
          <Text color="#4b5263" wrap="wrap">{out}</Text>
        </Box>
      )}
    </Box>
  )
}

// ─── 已完成消息 ────────────────────────────────────────────────────────────────
//
// Human:
//   消息内容
//
// (assistant 直接显示内容, 不加标签，跟 Claude Code 一样)
//   工具调用...
//   正文内容...
//
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
  // assistant
  return (
    <Box flexDirection="column" marginBottom={1}>
      {m.tools?.map((t, i) => (
        <ToolRow key={i} t={t} active={false} spinChar="" />
      ))}
      {m.text
        ? <Box paddingLeft={0}><Multiline text={m.text} /></Box>
        : null
      }
    </Box>
  )
}

// ─── 流式消息 ─────────────────────────────────────────────────────────────────
function LiveMsg({ stream, busy, spinChar }) {
  if (!stream && !busy) return null
  return (
    <Box flexDirection="column" marginBottom={1}>
      {/* 正在思考中（还没有任何输出） */}
      {busy && !stream?.text && !stream?.tools?.length && !stream?.cur && (
        <Box>
          <Text color="#528bff">{spinChar}</Text>
          <Text color="#4b5263" italic>  Thinking…</Text>
        </Box>
      )}
      {stream && (
        <>
          {/* 已完成的工具 */}
          {stream.tools.map((t, i) => (
            <ToolRow key={i} t={t} active={false} spinChar="" />
          ))}
          {/* 正在执行的工具 */}
          {stream.cur && (
            <ToolRow t={stream.cur} active spinChar={spinChar} />
          )}
          {/* 流式文本 + 光标 */}
          {stream.text && (
            <Box flexDirection="column">
              <Multiline text={stream.text} />
              {/* 末尾追加光标块 */}
              <Box><Text color="#528bff">{spinChar}</Text></Box>
            </Box>
          )}
        </>
      )}
    </Box>
  )
}

// ─── 标题栏 ───────────────────────────────────────────────────────────────────
//
// 仿 Claude Code:  ◆ Claude Code (model)        [mode]
//
function Header({ mode, busy, spinChar }) {
  const m = META[mode] ?? META.chat
  return (
    <Box justifyContent="space-between" paddingX={1}>
      {/* 左侧：图标 + 名称 */}
      <Box gap={1}>
        <Text color="#528bff" bold>◆</Text>
        <Text bold>Claude</Text>
        <Text color="#4b5263">·</Text>
        <Text color="#5c6370">AI 运维智能体</Text>
        {busy && (
          <>
            <Text color="#4b5263">·</Text>
            <Text color="#5c6370" italic>thinking {spinChar}</Text>
          </>
        )}
      </Box>
      {/* 右侧：模式标签 */}
      <Box gap={1}>
        <Text color={m.badge} bold>{m.label}</Text>
        <Text color="#4b5263" italic>{m.desc}</Text>
      </Box>
    </Box>
  )
}

// ─── 分割线 ───────────────────────────────────────────────────────────────────
function HR({ bright }) {
  return (
    <Box>
      <Text color={bright ? '#3e4451' : '#21252b'}>
        {'─'.repeat(W)}
      </Text>
    </Box>
  )
}

// ─── 底部工具栏 ───────────────────────────────────────────────────────────────
//
// 仿 Claude Code 底栏：模式切换 + 快捷键提示
//
function Footer({ mode }) {
  return (
    <Box paddingX={1} gap={3} marginTop={0}>
      {/* 模式快速切换 */}
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
      <Text color="#3e4451">tab</Text>
      <Text color="#3e4451">ctrl+r reset</Text>
      <Text color="#3e4451">ctrl+l clear</Text>
      <Text color="#3e4451">ctrl+c exit</Text>
    </Box>
  )
}

// ─── 错误横幅 ─────────────────────────────────────────────────────────────────
function ErrBanner({ msg }) {
  if (!msg) return null
  return (
    <Box paddingX={2} paddingY={0} marginBottom={1}>
      <Text color="#e06c75">✖  </Text>
      <Text color="#e06c75" wrap="wrap">{msg}</Text>
      <Text color="#4b5263">  (esc)</Text>
    </Box>
  )
}

// ─── 欢迎屏 ───────────────────────────────────────────────────────────────────
function Welcome() {
  return (
    <Box flexDirection="column" paddingX={1} marginBottom={1}>
      <Text color="#5c6370">
        {'  ✻ '}
        <Text color="#abb2bf">Welcome to </Text>
        <Text color="#528bff" bold>AI Ops Agent</Text>
        <Text color="#abb2bf">, your intelligent operations assistant.</Text>
      </Text>
      <Text color="#4b5263">
        {'    Use '}
        <Text color="#e5c07b">natural language</Text>
        {' to query logs, inspect hosts, analyze errors, and generate reports.'}
      </Text>
      <Text color="#4b5263">
        {'    Press '}
        <Text color="#e5c07b">Tab</Text>
        {' to switch modes, '}
        <Text color="#e5c07b">Enter</Text>
        {' to send.'}
      </Text>
    </Box>
  )
}

// ─── 主程序 ───────────────────────────────────────────────────────────────────
function App() {
  const { exit }          = useApp()
  const [s, dispatch]     = useReducer(reducer, INIT)

  // spinner 动画
  useEffect(() => {
    if (!s.busy && !s.stream) return
    const id = setInterval(() => dispatch({ type: 'TICK' }), 80)
    return () => clearInterval(id)
  }, [s.busy, !!s.stream])

  // 发送消息
  const send = useCallback(() => {
    if (!s.input.trim() || s.busy) return
    const msg = s.input.trim()
    dispatch({ type: 'SEND' })
    callAgent(s.mode, msg, s.convId, dispatch)
  }, [s.input, s.busy, s.mode, s.convId])

  // 键盘
  useInput((ch, key) => {
    if (key.ctrl) {
      if (ch === 'c') { exit(); return }
      if (ch === 'r') { dispatch({ type: 'RESET' }); return }
      if (ch === 'l') { dispatch({ type: 'CLEAR' }); return }
    }
    if (key.tab)    { const i = MODES.indexOf(s.mode); dispatch({ type: 'MODE', v: MODES[(i+1)%MODES.length] }); return }
    if (key.escape) { dispatch({ type: 'CLR_ERR' }); return }
  })

  const spinChar = SPIN_FRAMES[s.frame]
  const empty    = s.hist.length === 0 && !s.stream && !s.busy

  return (
    <Box flexDirection="column" width={W}>

      {/* ── 标题 ── */}
      <Header mode={s.mode} busy={s.busy} spinChar={spinChar} />
      <HR bright />
      <Box height={1} />

      {/* ── 欢迎（仅首次） ── */}
      {empty && <Welcome />}

      {/*
        ── 历史消息 ──
        Static 保证已完成消息只渲染一次，防止长对话闪烁
      */}
      <Static items={s.hist} key={s.epoch}>
        {m => <HistMsg key={m.id} m={m} />}
      </Static>

      {/* ── 流式消息 ── */}
      <LiveMsg stream={s.stream} busy={s.busy} spinChar={spinChar} />

      {/* ── 错误 ── */}
      <ErrBanner msg={s.err} />

      {/* ── 输入区（仿 Claude Code 的 > prompt） ── */}
      <HR />
      <Box paddingX={1} paddingY={0}>
        <Text color={s.busy ? '#3e4451' : '#528bff'} bold>{'> '}</Text>
        <TextInput
          value={s.input}
          onChange={v => dispatch({ type: 'INPUT', v })}
          onSubmit={send}
          placeholder={s.busy ? '' : 'Send a message…'}
          focus={!s.busy}
        />
      </Box>
      <HR />

      {/* ── 底栏 ── */}
      <Footer mode={s.mode} />
      <Box height={1} />

    </Box>
  )
}

// ─── 启动 ──────────────────────────────────────────────────────────────────────
if (!process.stdin.isTTY) {
  console.error('Error: raw mode requires an interactive terminal (TTY).')
  console.error('Run: node dist/index.mjs')
  process.exit(1)
}

render(<App />, { patchConsole: false })
