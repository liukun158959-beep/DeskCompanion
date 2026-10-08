const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load({ status = 200, source = 'var Live2DCubismCore = {};', script = 'ready' } = {}) {
  let appended = false;
  const window = {};
  const context = { exports: {}, fetch: async () => ({ ok: status === 200, status, text: async () => source }),
    AbortController, setTimeout, clearTimeout, Error, TypeError, window,
    document: { createElement: () => ({ remove() {} }), head: { appendChild(node) {
      appended = true;
      if (script === 'error') node.onerror();
      else { if (script === 'ready') window.Live2DCubismCore = { Version: { csmGetVersion() { return 1; } } }; node.onload(); }
    } } } };
  const sourcePath = path.resolve(__dirname, '../src/pet-assets.ts');
  const compiled = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(compiled, context);
  return { ...context.exports, appended: () => appended };
}
test('Core loads as a script and verifies SDK initialization', async () => {
  const api = load();
  await api.loadCubismCore('http://local/Core/live2dcubismcore.js', 'assets/Core/live2dcubismcore.js');
  assert.equal(api.appended(), true);
});
test('missing or invalid Core reports file and does not inject an invalid script', async () => {
  const missing = load({ status: 404 });
  await assert.rejects(missing.loadCubismCore('http://local/Core.js', 'C:/assets/Core.js'), /HTTP 404.*C:\/assets\/Core.js/);
  assert.equal(missing.appended(), false);
  for (const source of ['', '<html>fallback</html>', '// not a Core file']) {
    const invalid = load({ source });
    await assert.rejects(invalid.loadCubismCore('http://local/Core.js', 'C:/assets/Core.js'), /文件内容无效/);
    assert.equal(invalid.appended(), false);
  }
});
test('script failures and empty SDK initialization show a useful error', async () => {
  for (const script of ['error', 'empty']) {
    const api = load({ script });
    await assert.rejects(api.loadCubismCore('http://local/Core.js', 'C:/assets/Core.js'), /Cubism Core.*文件：C:\/assets\/Core.js/);
  }
});
test('error bubble removes duplicate punctuation and Error prefix', () => {
  const api = load();
  const message = api.petErrorText(new Error('加载失败。'));
  assert.ok(!message.includes('。。'));
  assert.ok(!message.includes('Error:'));
});
