#!/usr/bin/env node
// Runs a Workflow script the way the Workflow tool does — the body wrapped in one async
// function whose parameters are the hook globals — against scripted agent replies, so the
// orchestration logic is asserted without spawning an agent.
//
//   node tests/ship_dev_plan_harness.mjs <script.js> <scenario.json>
//   scenario = { args: <the Workflow args>, replies: { "<agent label>": <object | null> } }
//
// A label the scenario does not list throws: an agent call the test did not expect is a
// failure, not a default. Output is one `key=value` line per fact so a shell suite can grep it.
import { readFileSync } from 'node:fs'

const [scriptPath, scenarioPath] = process.argv.slice(2)
const source = readFileSync(scriptPath, 'utf8')
const scenario = JSON.parse(readFileSync(scenarioPath, 'utf8'))

const META_HEAD = 'export const meta = '
if (!source.startsWith(META_HEAD)) {
  console.error('script must begin with `export const meta = {...}`')
  process.exit(2)
}
const body = 'const meta = globalThis.__meta = ' + source.slice(META_HEAD.length)

const calls = []
const phases = []
const logs = []

async function agent(prompt, opts = {}) {
  const label = opts.label ?? `agent#${calls.length}`
  calls.push({ label, phase: opts.phase ?? null, isolation: opts.isolation ?? null, schema: Boolean(opts.schema), prompt })
  if (!(label in scenario.replies)) throw new Error(`unexpected agent call: ${label}`)
  return scenario.replies[label]
}

const hooks = {
  agent,
  parallel: async thunks => Promise.all(thunks.map(t => t().catch(() => null))),
  pipeline: async () => { throw new Error('pipeline() is not modelled by this harness') },
  log: message => logs.push(message),
  phase: title => phases.push(title),
  args: scenario.args,
  budget: { total: null, spent: () => 0, remaining: () => Infinity },
  workflow: async () => { throw new Error('workflow() is not modelled by this harness') },
}

const AsyncFunction = (async () => {}).constructor
const run = new AsyncFunction(...Object.keys(hooks), body)
const result = await run(...Object.values(hooks))

const out = line => process.stdout.write(line + '\n')
out(`meta=${JSON.stringify(globalThis.__meta)}`)
out(`result=${JSON.stringify(result)}`)
out(`calls=${calls.map(c => c.label).join(',')}`)
out(`phases=${phases.join(',')}`)
out(`logs=${logs.length}`)
for (const c of calls) {
  out(`call:${c.label}=${JSON.stringify({ phase: c.phase, isolation: c.isolation, schema: c.schema })}`)
  out(`prompt:${c.label}=${JSON.stringify(c.prompt)}`)
}
