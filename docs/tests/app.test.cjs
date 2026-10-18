const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

function app() {
  const context = vm.createContext({
    localStorage: { getItem: () => null },
    document: {
      querySelector: () => ({ addEventListener() {} }),
      querySelectorAll: () => [],
      getElementById: () => ({
        addEventListener() {},
        setAttribute() {},
        style: {},
      }),
    },
    fetch: () => new Promise(() => {}),
    URL,
    AbortSignal,
    setTimeout,
    clearTimeout,
    Intl,
    Date,
  });
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../app.js"), "utf8"),
    context,
  );
  return context;
}

test("feed order survives the snapshot join for all ranked tabs", () => {
  const context = app();
  vm.runInContext(
    `
    state.programs = [{id:'low', platform:'hackerone'}, {id:'high', platform:'bugcrowd'}];
    state.feeds = {
      recommended: [{id:'high'}, {id:'missing'}, {id:'low'}],
      easy: [{id:'high'}, {id:'low'}], new: [{id:'high'}, {id:'low'}],
      recommended_by_platform: { hackerone: [{id:'low'}], bugcrowd: [] }
    };
  `,
    context,
  );
  for (const tab of ["recommended", "easy", "new"]) {
    const ids = vm.runInContext(
      `state.tab='${tab}'; JSON.stringify(tabRows().map(p=>p.id))`,
      context,
    );
    assert.deepEqual(JSON.parse(ids), ["high", "low"]);
  }
  assert.equal(
    vm.runInContext(
      `state.tab='recommended'; state.platform='bugcrowd'; tabRows().length`,
      context,
    ),
    0,
  );
  assert.equal(
    vm.runInContext(`state.platform='hackerone'; tabRows()[0].id`, context),
    "low",
  );
});

test("reward threshold compares known maxima in the selected currency", () => {
  const context = app();
  vm.runInContext(
    `
    state.tab='all'; state.minb='100'; state.currency='USD';
    state.programs=[
      {id:'usd', currency:'USD', max_bounty:150},
      {id:'eur', currency:'EUR', max_bounty:200},
      {id:'btc', currency:'BTC', max_bounty:200},
      {id:'unknown-max', currency:'USD', min_bounty:500},
      {id:'small', currency:'USD', max_bounty:50}
    ];
  `,
    context,
  );
  assert.deepEqual(
    JSON.parse(
      vm.runInContext("JSON.stringify(currentRows().map(p=>p.id))", context),
    ),
    ["usd"],
  );
  assert.equal(
    vm.runInContext("state.currency=''; currentRows().length", context),
    0,
  );
  assert.equal(
    vm.runInContext("state.minb=''; currentRows().length", context),
    5,
  );
});

test("history describes zero, false and exclusion changes", () => {
  const context = app();
  const text = vm.runInContext(
    `historyText({at:'today',name:'Demo',kind:'program_changes',
    fields:{max_bounty:{before:100,after:0}, offers_bounty:{before:true,after:false}},
    scopes:{out_of_scope:{added:['admin.demo.test'],removed:[],updated:[]}}})`,
    context,
  );
  assert.match(text, /100 → 0/);
  assert.match(text, /true → false/);
  assert.match(text, /Ngoài scope thêm: admin.demo.test/);
});

test("large lists page by 50 and cards open with keyboard", () => {
  const context = app();
  vm.runInContext(
    `
    const list = {children:[], set innerHTML(value){if(value==='')this.children=[]},
      appendChild(el){this.children.push(el)}};
    const status = {textContent:'',focus(){}};
    document.getElementById = id => id === 'list' ? list : id === 'list-status' ? status : {textContent:''};
    document.createElement = tag => ({tag, dataset:{}, listeners:{},
      setAttribute(){}, addEventListener(name, fn){this.listeners[name]=fn}});
    state.tab='all'; state.programs = Array.from({length: 120}, (_, i) =>
      ({id:'id'+i,name:'Program '+i,platform:'self-host',in_scope:[],reward_types:['unknown']}));
    show = p => { state.openId = p.id; };
    render();
  `,
    context,
  );
  assert.equal(
    vm.runInContext(
      'list.children.filter(x=>x.tag==="article").length',
      context,
    ),
    50,
  );
  assert.match(vm.runInContext("status.textContent", context), /50\/120/);
  vm.runInContext(
    `list.children[0].listeners.keydown({key:'Enter',target:list.children[0],preventDefault(){}});`,
    context,
  );
  assert.equal(vm.runInContext("state.openId", context), "id0");
  vm.runInContext(`list.children.at(-1).listeners.click();`, context);
  assert.equal(
    vm.runInContext(
      'list.children.filter(x=>x.tag==="article").length',
      context,
    ),
    100,
  );
});

test("policy links reject non-http schemes", () => {
  const context = app();
  assert.equal(
    vm.runInContext("safeHttpUrl('javascript:alert(1)')", context),
    false,
  );
  assert.equal(
    vm.runInContext("safeHttpUrl('https://example.org/security')", context),
    true,
  );
});

test("saved data validates legacy and versioned imports without accepting malformed entries", () => {
  const c = app();
  for (const raw of [
    "42",
    "[]",
    '"text"',
    "{a:{note:42}}",
    "{version:2,items:{}}",
    '{a:{note:"x".repeat(20001)}}',
  ]) {
    assert.throws(() => vm.runInContext(`normalizeSaved(${raw})`, c));
  }
  assert.throws(() =>
    vm.runInContext(
      `normalizeSaved(JSON.parse('{"__proto__":{"note":"x"}}'))`,
      c,
    ),
  );
  const raw = vm.runInContext(
    `JSON.stringify(normalizeSaved({version:1,items:{'self-host:demo':{note:'hello',program:{name:'Demo',url:'https://demo.test'}}}}))`,
    c,
  );
  assert.equal(JSON.parse(raw)["self-host:demo"].note, "hello");
  assert.equal(
    vm.runInContext(`normalizeSaved({'legacy':{note:'old'}}).legacy.note`, c),
    "old",
  );
});

test("storage failure retains the note in memory and reports that it is not persisted", () => {
  const c = app();
  vm.runInContext(
    `localStorage.setItem=()=>{throw new Error('QuotaExceededError')}; state.saved={demo:{note:'keep'}};`,
    c,
  );
  assert.equal(vm.runInContext("persistSaved()", c), false);
  assert.equal(vm.runInContext("state.saved.demo.note", c), "keep");
  assert.match(vm.runInContext("storageWarning", c), /Chưa lưu được/);
});

test("saved programs remain available when no longer in the live feed", () => {
  const c = app();
  vm.runInContext(
    `state.tab='saved'; state.programs=[]; state.saved={'hackerone:old':{note:'research',program:{name:'Old program',platform:'hackerone'}}};`,
    c,
  );
  assert.equal(vm.runInContext("tabRows()[0].name", c), "Old program");
  assert.equal(vm.runInContext("tabRows()[0].unavailable", c), true);
});

test("malformed original storage is backed up before a new collection replaces it", () => {
  const c = app();
  vm.runInContext(
    `const writes=[]; localStorage.getItem=()=>'{broken'; localStorage.setItem=(key,value)=>writes.push([key,value]); state.saved=loadSaved(); state.saved.demo={note:'new'};`,
    c,
  );
  assert.equal(vm.runInContext("persistSaved()", c), true);
  assert.equal(vm.runInContext("writes[0][0]", c), "bbh-saved-v1.recovery");
  assert.equal(vm.runInContext("writes[0][1]", c), "{broken");
  assert.equal(vm.runInContext("writes[1][0]", c), "bbh-saved-v1");
});
