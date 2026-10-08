const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { create, act } = require('react-test-renderer');

const filename = path.resolve(__dirname, '../src/client/onboarding.tsx');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
function mount(rpc) {
  const mod = new Module(filename, module);
  mod.filename = filename; mod.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = mod.require.bind(mod);
  mod.require = (id) => id === './api' ? { rpc } : original(id);
  mod._compile(compiled, filename);
  const props = { info: { port: 1, token: 'test' },
    status: { ok: true, show: true, configured: false, data_dir: 'isolated-data', assets_dir: 'isolated-assets', checks: {} },
    models: { ok: true, active: '', items: [] }, onModels: (value) => { props.models = value; renderer.update(React.createElement(mod.exports.SetupGuide, props)); },
    onClose: () => { props.closed = true; }, onNavigate: (pane, sub) => { props.target = [pane, sub]; } };
  let renderer;
  act(() => { renderer = create(React.createElement(mod.exports.SetupGuide, props)); });
  const button = (label) => renderer.root.findAllByType('button').find((node) => node.children.join('') === label);
  return { renderer, props, button };
}
test('first-run model save uses shared API, clears key, then persists completion', async () => {
  const calls = [];
  const app = mount(async (_info, method, args) => {
    calls.push([method, args]);
    return method === 'save_model_entry' ? { ok: true, active: 'm1', items: [{ id: 'm1', model: 'test', base_url: 'https://example.com/v1', has_key: true }] } : { ok: true, message: 'connected' };
  });
  act(() => app.button('开始配置').props.onClick());
  const fields = app.renderer.root.findAllByType('input');
  act(() => fields.forEach((node, i) => node.props.onChange({ target: { value: ['https://example.com/v1', 'test', 'test-key'][i] } })));
  await act(async () => app.button('保存模型').props.onClick());
  assert.equal(calls[0][0], 'save_model_entry');
  assert.equal(calls[0][1].payload.api_key, 'test-key');
  assert.equal(app.renderer.root.findAllByType('input')[2].props.value, '');
  await act(async () => app.button('测试连通').props.onClick());
  assert.equal(calls[1][1].payload.id, 'm1');
  assert.equal(calls[1][1].payload.api_key, '');
  act(() => app.button('继续').props.onClick());
  await act(async () => app.button('完成引导').props.onClick());
  assert.equal(calls[2][0], 'complete_onboarding');
  assert.equal(app.props.closed, true);
  app.renderer.unmount();
});
test('failed save stays on model step and exposes error without declaring readiness', async () => {
  const app = mount(async () => ({ ok: false, error: 'invalid address' }));
  act(() => app.button('开始配置').props.onClick());
  await act(async () => app.button('保存模型').props.onClick());
  assert.equal(app.button('继续').props.disabled, true);
  assert.equal(app.renderer.root.findByProps({ role: 'alert' }).children.join(''), 'Error: invalid address');
  act(() => app.button('稍后设置').props.onClick());
  assert.equal(app.props.closed, true);
  app.renderer.unmount();
});
test('optional-feature navigation persists completion before leaving guide', async () => {
  const calls = [];
  const app = mount(async (_info, method) => { calls.push(method); return { ok: true }; });
  act(() => app.button('开始配置').props.onClick());
  act(() => app.button('先浏览，稍后配置').props.onClick());
  const links = app.renderer.root.findAllByType('button').filter((node) => node.children.join('') === '前往设置');
  await act(async () => links[3].props.onClick());
  assert.deepEqual(calls, ['complete_onboarding']);
  assert.deepEqual(app.props.target, ['board', 'knowledge']);
  app.renderer.unmount();
});
