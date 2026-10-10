const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');

function load(name, mocks = {}) {
  const filename = path.resolve(__dirname, '../src/client/' + name + '.tsx');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const mod = new Module(filename, module); mod.filename = filename; mod.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = mod.require.bind(mod); mod.require = id => mocks[id] || original(id); mod._compile(compiled, filename); return mod.exports;
}

test('wiki groups use stable space identity and retain local and unclassified documents', () => {
  const { groupSources } = load('knowledge');
  const groups = groupSources([{ space_id:'s1',space_name:'技术库',title:'a' }, { space_id:'s2',space_name:'技术库',title:'b' },
    { space_id:'s1',space_name:'技术库',title:'c' }, { source:'local',title:'d' }, { url:'https://x/wiki/a',title:'e' }, { title:'f' }]);
  assert.equal(groups.length, 5); assert.equal(groups[0].items.length, 2); assert.notEqual(groups[0].id,groups[1].id);
});

test('attachment dialog selects nested files, previews full pages, and attaches only chosen items', async () => {
  const calls = []; let attached, indexed = [];
  const file = { id:'file',kind:'file',name:'资料.md',relative:'子目录/资料.md',path:'E:/资料/子目录/资料.md',chars:4 };
  const folder = { id:'folder',kind:'folder',name:'资料',path:'E:/资料',chars:4,files:[file],skipped:2 };
  const rpc = async (_info,name,args) => {
    calls.push([name,args]);
    if (name === 'pick_local_sources') return { ok:true,sources:[folder],errors:[{name:'bad.pdf',error:'没有文字'}] };
    if (name === 'read_local_source') return { ok:true,source:{text:args.offset ? '结尾' : '开头',next_offset:args.offset ? null : 2,chars:4} };
  };
  const { LocalSourcesDialog } = load('local-sources',{ './api':{rpc} });
  let view;
  await act(async () => { view = create(React.createElement(LocalSourcesDialog,{info:{port:1,token:'test'},initialKind:'folder',onClose(){},onAttach:s => attached=s,onIndex:async s => { indexed.push(s.id);return {ok:true,error:''}; }})); });
  const button = label => view.root.findAllByType('button').find(b => b.children.join('') === label);
  assert.equal(calls.length, 0, 'opening the panel must not open a native picker or steal focus');
  assert.equal(view.root.findByProps({role:'dialog'}).props['aria-modal'], 'false');
  await act(async () => button('选择文件夹').props.onClick());
  assert.equal(calls[0][1].kind, 'folder'); assert.match(JSON.stringify(view.toJSON()),/bad.pdf/);
  act(() => view.root.findByProps({'aria-label':'选择 子目录/资料.md'}).props.onChange({target:{checked:true}}));
  await act(async () => button('预览').props.onClick());
  await act(async () => button('继续读取').props.onClick());
  assert.ok(view.root.findByType('pre').children.join('').includes('开头结尾'));
  await act(async () => button('加入知识库').props.onClick()); assert.deepEqual(indexed,['file']);
  act(() => button('附到对话（1）').props.onClick()); assert.deepEqual(attached.map(s => s.id),['file']);
  act(() => view.unmount());
});

test('cancelled picker creates no attachment and shows no stale preview', async () => {
  const { LocalSourcesDialog } = load('local-sources',{ './api':{rpc:async () => ({ok:true,sources:[],errors:[]})} });
  let view;
  await act(async () => { view = create(React.createElement(LocalSourcesDialog,{info:{port:1,token:'test'},initialKind:'file',onClose(){},onAttach(){},onIndex:async () => ({ok:true})})); });
  assert.equal(view.root.findAllByType('button').find(b => b.children.join('') === '附到对话（0）').props.disabled,true);
  act(() => view.unmount());
});

test('loading panel can minimize and close, cancels its own picker and ignores late results', async () => {
  let finish, closed = 0; const calls = [];
  const { LocalSourcesDialog } = load('local-sources', { './api': { rpc: async (_info, method, args) => {
    calls.push([method,args]);
    if (method === 'pick_local_sources') return new Promise(resolve => { finish = resolve; });
    return {ok:true};
  } } });
  let view;
  await act(async () => { view=create(React.createElement(LocalSourcesDialog,{info:{port:1,token:'test'},initialKind:'file',onClose(){closed++;},onAttach(){},onIndex:async()=>({ok:true})})); });
  const button = label => view.root.findAllByType('button').find(b => b.children.join('')===label);
  act(() => button('选择文件').props.onClick());
  assert.equal(button('关闭').props.disabled, undefined);
  act(() => button('收起').props.onClick()); assert.ok(button('展开'));
  act(() => button('关闭').props.onClick()); assert.equal(closed,1);
  assert.deepEqual(calls[1],['cancel_local_source_request',{request_id:calls[0][1].request_id}]);
  await act(async () => finish({ok:true,sources:[{id:'late',kind:'file',name:'迟到的文件',chars:2}],errors:[]}));
  assert.ok(!JSON.stringify(view.toJSON()).includes('迟到的文件'));
  act(() => view.unmount());
});

test('closing during batch indexing lets current file finish but does not queue more files', async () => {
  let finish; const indexed=[];
  const { LocalSourcesDialog }=load('local-sources',{'./api':{rpc:async()=>({ok:true,sources:[
    {id:'one',kind:'file',name:'one.md',chars:1},{id:'two',kind:'file',name:'two.md',chars:1}],errors:[]})}});
  let view;
  await act(async()=>{view=create(React.createElement(LocalSourcesDialog,{info:{port:1,token:'test'},initialKind:'file',onClose(){},onAttach(){},onIndex:async s=>{indexed.push(s.id);return new Promise(resolve=>{finish=resolve;});}}));});
  const button=label=>view.root.findAllByType('button').find(b=>b.children.join('')===label);
  await act(async()=>button('选择文件').props.onClick());
  act(()=>button('加入知识库').props.onClick());
  act(()=>button('关闭').props.onClick());
  await act(async()=>finish({ok:true,error:''}));
  assert.deepEqual(indexed,['one']); act(()=>view.unmount());
});
