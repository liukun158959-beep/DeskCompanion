const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');

function load(rpc) {
  const filename = path.resolve(__dirname, '../src/client/video.tsx');
  const mod = new Module(filename, module);
  mod.filename = filename; mod.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = mod.require.bind(mod);
  mod.require = id => id === './api' ? { rpc } : id === './Markdown' ? { MdLink: props => React.createElement('a', { href: props.href }, props.children) } : original(id);
  mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
  return mod.exports;
}
global.window = { setInterval: () => 1, clearInterval() {} };

test('video settings wait for existing values before save and keep optional network fields', async () => {
  const calls = [];
  const rpc = async (_, method, args) => { calls.push([method, args]); return { settings: { proxy: 'http://127.0.0.1:7890', cookie_file: 'C:/user/cookies.txt' } }; };
  const { VideoSettings } = load(rpc);
  let renderer;
  await act(async () => { renderer = create(React.createElement(VideoSettings, { info: { port: 1 } })); });
  assert.equal(renderer.root.findAllByType('input')[0].props.value, 'http://127.0.0.1:7890');
  await act(async () => renderer.root.findByType('button').props.onClick());
  assert.deepEqual(calls.at(-1), ['save_video_settings', { proxy: 'http://127.0.0.1:7890', cookie_file: 'C:/user/cookies.txt' }]);
  act(() => renderer.unmount());
});

test('video evidence states subtitle limits and saves only completed selected task', async () => {
  const calls = [];
  const source = { source_id: 'a'.repeat(24), title: 'Video', author: 'Author', url: 'https://youtu.be/abcdefghijk',
    platform: 'YouTube', subtitle_notice: '自动字幕可能有误', subtitle_language: 'en', segment_count: 4, chapters: [] };
  const rpc = async (_, method, args) => { calls.push([method, args]); return method === 'list_task_videos' ? { items: [source] } : { url: 'https://example.feishu.cn/docx/note' }; };
  const { TaskVideos } = load(rpc);
  let renderer;
  await act(async () => { renderer = create(React.createElement(TaskVideos, { info: { port: 1 }, taskId: 'task-a', state: 'running' })); });
  assert.ok(JSON.stringify(renderer.toJSON()).includes('自动字幕可能有误'));
  assert.equal(renderer.root.findByType('button').props.disabled, true);
  await act(async () => renderer.update(React.createElement(TaskVideos, { info: { port: 1 }, taskId: 'task-a', state: 'succeeded' })));
  await act(async () => renderer.root.findByType('button').props.onClick());
  assert.deepEqual(calls.at(-1), ['export_task_video', { task_id: 'task-a', source_id: source.source_id }]);
  assert.ok(JSON.stringify(renderer.toJSON()).includes('打开视频笔记'));
  act(() => renderer.unmount());
});
