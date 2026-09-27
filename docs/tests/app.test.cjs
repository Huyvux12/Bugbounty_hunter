const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function app() {
  const context = vm.createContext({
    localStorage: { getItem: () => null },
    document: { querySelector: () => ({ addEventListener() {} }), querySelectorAll: () => [], getElementById: () => ({ addEventListener() {} }) },
    fetch: () => new Promise(() => {}),
    URL,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8'), context);
  return context;
}

test('feed order survives the snapshot join for all ranked tabs', () => {
  const context = app();
  vm.runInContext(`
    state.programs = [{id:'low', platform:'hackerone'}, {id:'high', platform:'bugcrowd'}];
    state.feeds = {
      recommended: [{id:'high'}, {id:'missing'}, {id:'low'}],
      easy: [{id:'high'}, {id:'low'}], new: [{id:'high'}, {id:'low'}],
      recommended_by_platform: { hackerone: [{id:'low'}], bugcrowd: [] }
    };
  `, context);
  for (const tab of ['recommended', 'easy', 'new']) {
    const ids = vm.runInContext(`state.tab='${tab}'; JSON.stringify(tabRows().map(p=>p.id))`, context);
    assert.deepEqual(JSON.parse(ids), ['high', 'low']);
  }
  assert.equal(vm.runInContext(`state.tab='recommended'; state.platform='bugcrowd'; tabRows().length`, context), 0);
  assert.equal(vm.runInContext(`state.platform='hackerone'; tabRows()[0].id`, context), 'low');
});

test('reward threshold compares known maxima in the selected currency', () => {
  const context = app();
  vm.runInContext(`
    state.tab='all'; state.minb='100'; state.currency='USD';
    state.programs=[
      {id:'usd', currency:'USD', max_bounty:150},
      {id:'eur', currency:'EUR', max_bounty:200},
      {id:'btc', currency:'BTC', max_bounty:200},
      {id:'unknown-max', currency:'USD', min_bounty:500},
      {id:'small', currency:'USD', max_bounty:50}
    ];
  `, context);
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(currentRows().map(p=>p.id))',context)), ['usd']);
  assert.equal(vm.runInContext("state.currency=''; currentRows().length", context), 0);
  assert.equal(vm.runInContext("state.minb=''; currentRows().length", context), 5);
});

test('history describes zero, false and exclusion changes', () => {
  const context = app();
  const text = vm.runInContext(`historyText({at:'today',name:'Demo',kind:'program_changes',
    fields:{max_bounty:{before:100,after:0}, offers_bounty:{before:true,after:false}},
    scopes:{out_of_scope:{added:['admin.demo.test'],removed:[],updated:[]}}})`, context);
  assert.match(text, /100 → 0/);
  assert.match(text, /true → false/);
  assert.match(text, /Ngoài scope thêm: admin.demo.test/);
});

test('large lists page by 50 and cards open with keyboard', () => {
  const context = app();
  vm.runInContext(`
    const list = {children:[], set innerHTML(value){if(value==='')this.children=[]},
      appendChild(el){this.children.push(el)}};
    const status = {textContent:'',focus(){}};
    document.getElementById = id => id === 'list' ? list : status;
    document.createElement = tag => ({tag, dataset:{}, listeners:{},
      setAttribute(){}, addEventListener(name, fn){this.listeners[name]=fn}});
    state.tab='all'; state.programs = Array.from({length: 120}, (_, i) =>
      ({id:'id'+i,name:'Program '+i,platform:'self-host',in_scope:[],reward_types:['unknown']}));
    show = p => { state.openId = p.id; };
    render();
  `, context);
  assert.equal(vm.runInContext('list.children.filter(x=>x.tag==="article").length', context), 50);
  assert.match(vm.runInContext('status.textContent', context), /50\/120/);
  vm.runInContext(`list.children[0].listeners.keydown({key:'Enter',preventDefault(){}});`, context);
  assert.equal(vm.runInContext('state.openId', context), 'id0');
  vm.runInContext(`list.children.at(-1).listeners.click();`, context);
  assert.equal(vm.runInContext('list.children.filter(x=>x.tag==="article").length', context), 100);
});

test('policy links reject non-http schemes', () => {
  const context = app();
  assert.equal(vm.runInContext("safeHttpUrl('javascript:alert(1)')", context), false);
  assert.equal(vm.runInContext("safeHttpUrl('https://example.org/security')", context), true);
});
