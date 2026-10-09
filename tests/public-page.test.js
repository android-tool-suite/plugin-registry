const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../public/index.html'),'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.attributes={}; this.listeners={}; this.dataset={}; this.value=''; this.hidden=false; this.text=''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; this.text=''; }
  setAttribute(key,value) { this.attributes[key]=value; }
  removeAttribute(key) { delete this.attributes[key]; delete this[key]; }
  addEventListener(event,handler) { this.listeners[event]=handler; }
  focus() { this.focused=true; }
  set textContent(value) { this.text=String(value); this.children=[]; }
  get textContent() { return this.text + this.children.map(child => child.textContent || '').join(''); }
}
function release(name,code) { return {channel:'release',versionName:name,versionCode:code,tagName:'v'+name,publishedAt:'2026-09-19T08:00:00Z',size:123456,minAndroidApi:24,minHostVersionCode:23,downloadUrl:'https://example.test/'+code,releaseUrl:'https://example.test/releases/'+code,sha256:String(code).repeat(64).slice(0,64)}; }
function catalog() { return {schemaVersion:1,channel:'release',generatedAt:'2026-09-20T00:00:00Z',app:{versions:[release('2.0.0',2),release('1.0.0',1)]},plugins:[{id:'test.plugin',title:'真实目录夹具',author:'Test',description:'<script>literal description</script>',versions:[release('2.0.0',2),release('1.0.0',1)]}]}; }
async function setup() {
  const ids = new Map([...source.matchAll(/\bid="([^"]+)"/g)].map(match => ['#'+match[1],new Element('div')]));
  const context = {URL,Intl,Date,Map,Set,Number,decodeURIComponent,encodeURIComponent,
    location:{hash:''},document:{querySelector:id => ids.get(id),createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),documentElement:new Element('html')},
    navigator:{clipboard:{writeText:async()=>{}}},localStorage:{getItem:()=>null,setItem:()=>{}},
    fetch:async()=>({ok:true,json:async()=>catalog()}),
    window:{addEventListener(){},scrollTo(){}}};
  vm.createContext(context); vm.runInContext(script,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {context,ids,run:code=>vm.runInContext(code,context)};
}
function find(root,match) { if(match(root)) return root; for(const child of root.children) {const result=find(child,match); if(result)return result;} }
test('真实正式目录载入后只呈现其插件，不注入示例插件',async()=>{
  const {ids}=await setup();
  assert.equal(ids.get('#plugins').children.length,1);
  assert.match(ids.get('#plugins').textContent,/真实目录夹具/);
  assert.match(ids.get('#plugins').textContent,/<script>literal description<\/script>/);
  assert.equal(ids.get('#app').children[0].href,'https://example.test/2');
});
test('版本选择同时更新下载、校验值，并在重建面板后保留选择',async()=>{
  const {run}=await setup();
  const panel=run("createVersionPanel(currentCatalog.plugins[0].versions,'plugin:test.plugin',true)");
  const select=find(panel,item=>item.tagName==='select');
  select.value='1'; select.listeners.change();
  assert.equal(find(panel,item=>item.className==='button primary').href,'https://example.test/1');
  assert.equal(find(panel,item=>item.tagName==='code').textContent,'1'.repeat(64));
  const restored=run("createVersionPanel(currentCatalog.plugins[0].versions,'plugin:test.plugin',true)");
  assert.equal(find(restored,item=>item.tagName==='select').value,'1');
});
test('应用正式元数据的 minSdk 同样展示真实系统要求',async()=>{
  const {run,ids}=await setup();
  run('delete currentCatalog.app.versions[0].minAndroidApi; currentCatalog.app.versions[0].minSdk=24; renderApp();');
  assert.match(ids.get('#app').textContent,/Android 7\.0 或更高/);
  assert.match(ids.get('#app-versions').textContent,/Android 7\.0 或更高/);
});
test('插件详情使用真实目录，未知链接显示可返回的空态',async()=>{
  const {context,ids,run}=await setup();
  context.location.hash='#plugin/test.plugin';run('route(true)');
  assert.equal(ids.get('#catalog-page').hidden,true);
  assert.match(ids.get('#detail-page').textContent,/真实目录夹具/);
  context.location.hash='#plugin/missing';run('route()');
  assert.match(ids.get('#detail-page').textContent,/没有找到/);
  assert.equal(ids.get('#detail-page').children[0].href,'#catalog');
});
test('错误通道和非HTTPS下载链接不能变成可下载发布',async()=>{
  const {run}=await setup();
  assert.throws(()=>run("validateCatalog({schemaVersion:1,channel:'debug',app:{versions:[]},plugins:[]})"),/通道/);
  const link=run("action('下载','javascript:alert(1)',true)");
  assert.equal(link.href,undefined);
  assert.equal(link.attributes['aria-disabled'],'true');
});
test('刷新失败保留现有发布信息并开放重试',async()=>{
  const {context,ids,run}=await setup();
  const before=ids.get('#plugins').children[0];
  context.fetch=async()=>{throw new Error('offline')};
  await run('load()');
  assert.equal(ids.get('#plugins').children[0],before);
  assert.equal(ids.get('#retry').hidden,false);
  assert.match(ids.get('#status').textContent,/保留已读取内容/);
});
