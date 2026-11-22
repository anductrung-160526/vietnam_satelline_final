// node tests/test_snapshot_frontend.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {innerHTML:'', disabled:false, textContent:'', prepend(){}});
  return elements.get(id);
};
const requests = [];
let response;
const context = vm.createContext({
  $:element, banDo:null,
  document:{getElementById:element, createElement:()=>({})},
  fetch:async (url, options) => { requests.push({url, options}); return response; },
});
const demo = fs.readFileSync(path.join(root, 'frontend/demo.js'), 'utf8');
vm.runInContext(demo.slice(0, demo.indexOf('const CLASS_COLORS')), context);
const app = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');
vm.runInContext(app.slice(app.indexOf('async function layJSON('), app.indexOf('const dinhDang')), context);
const run = code => vm.runInContext(code, context);
const reply = (headers, body={}) => ({headers:new Headers(headers), ok:true, json:async()=>body});

(async () => {
  // Một phản hồi cũ không có header không được khởi tạo snapshot = null.
  response=reply({}); await run("layJSON('/api/health')");
  assert.equal(run('demoSnapshotInitialized'),false);
  response=reply({'X-Snapshot-ID':'dataset-a'}); await run("layJSON('/api/provinces')");
  assert.equal(run('demoSnapshotId'),'dataset-a');
  // Thiếu metadata giữa các phản hồi cũng không được báo đổi phiên bản.
  response=reply({}); await run("layJSON('/api/boundaries.geojson')");
  run('checkDemoSnapshot({})');
  run("checkDemoSnapshot({snapshot_id:'dataset-a'})");
  assert.equal(run('demoSnapshotChanged'),false);
  assert.ok(requests.every(r=>r.options.cache==='no-store'));
  // Có phiên bản mới thật vẫn khóa màn hình và yêu cầu tải lại.
  response=reply({'X-Snapshot-ID':'dataset-b'});
  await assert.rejects(run("layJSON('/api/panel')"), /Bộ dữ liệu đã được cập nhật/);
  assert.equal(run('demoSnapshotChanged'),true);
  console.log('Snapshot frontend: missing metadata, no-store, and real change passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
