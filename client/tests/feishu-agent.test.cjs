const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');

function mount(rpc) {
  const filename = path.resolve(__dirname, '../src/client/feishu-agent.tsx');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = new Module(filename, module);
  mod.filename = filename; mod.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = mod.require.bind(mod);
  mod.require = (id) => id === './api' ? { rpc } : id === '@tauri-apps/api/core' ? { isTauri: () => false } : original(id);
  mod._compile(compiled, filename);
  global.window = { setInterval: () => 1, clearInterval() {} };
  let renderer;
  act(() => { renderer = create(React.createElement(mod.exports.FeishuAgentPane, { info: { port: 1, token: 'test' } })); });
  return { renderer, button: (label) => renderer.root.findAllByType('button').find((node) => node.children.join('') === label) };
}
const idle = { ok: true, enabled: false, connected: false, state: 'stopped', error: '', diagnostic: '', last_reply: '', binding: {} };

test('Feishu page starts and stops bot connection through the shared API', async () => {
  const calls = [];
  const app = mount(async (_info, method) => {
    calls.push(method);
    return method === 'start_feishu_agent' ? { ...idle, enabled: true, connected: true, state: 'connected',
      binding: { app_id: 'test-app', app_name: '测试应用', owner_name: '测试用户' } } : idle;
  });
  await act(async () => {});
  await act(async () => app.button('接入飞书').props.onClick());
  assert.equal(app.button('接入飞书').props.disabled, true);
  assert.equal(app.button('停止接入').props.disabled, false);
  assert.ok(JSON.stringify(app.renderer.toJSON()).includes('测试用户'));
  await act(async () => app.button('停止接入').props.onClick());
  assert.deepEqual(calls, ['load_feishu_agent', 'start_feishu_agent', 'stop_feishu_agent']);
  assert.equal(app.button('接入飞书').props.disabled, false);
  app.renderer.unmount();
});
test('remote connection blocker stays visible with retry and stop actions', async () => {
  const app = mount(async () => ({ ...idle, enabled: true, state: 'error', error: '这个应用已有其他服务的长连接。' }));
  await act(async () => {});
  assert.ok(JSON.stringify(app.renderer.toJSON()).includes('其他服务的长连接'));
  assert.equal(app.button('重新接入').props.disabled, false);
  assert.equal(app.button('停止接入').props.disabled, false);
  app.renderer.unmount();
});
test('a failed binding or RPC remains actionable and never declares connected', async () => {
  const app = mount(async (_info, method) => {
    if (method === 'start_feishu_agent') throw new Error('机器人身份不可用');
    return idle;
  });
  await act(async () => {});
  await act(async () => app.button('接入飞书').props.onClick());
  assert.ok(JSON.stringify(app.renderer.toJSON()).includes('机器人身份不可用'));
  assert.equal(app.button('接入飞书').props.disabled, false);
  assert.equal(app.button('停止接入').props.disabled, true);
  app.renderer.unmount();
});
