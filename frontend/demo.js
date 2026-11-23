"use strict";
// Phần B: một ngữ cảnh tỉnh/năm/tháng, cùng kết quả cho bản đồ, Raw và Processed.
let demoSelection = {code:'01', year:2024, month:0};
let demoReady = false;
let sharedRequest = 0;
let demoRequest = 0;
let economyRequest = 0;
let economyChart = null;
let demoDetails = null;
let economyBasis = 'so_sanh';
const CLASS_NAMES = ['Tối / dưới ngưỡng nền','Sáng yếu','Sáng vừa','Sáng mạnh','Rất sáng'];
let demoSnapshotInitialized=false, demoSnapshotId=null, demoSnapshotChanged=false;
function checkDemoSnapshot(data){
  // Thiếu metadata nghĩa là chưa biết, không phải dataset đã bị xóa/đổi.
  if(!Object.prototype.hasOwnProperty.call(data,'snapshot_id'))return;
  const id=data.snapshot_id || null;
  if(demoSnapshotChanged || (demoSnapshotInitialized && id!==demoSnapshotId)){
    demoSnapshotChanged=true;demoDetails=null;
    if(typeof invalidateWideTable==='function')invalidateWideTable();
    if(typeof invalidateSpatial==='function')invalidateSpatial();
    $('class-summary').innerHTML='';$('nut-tai-anh').disabled=true;
    const message='Bộ dữ liệu đã được cập nhật. Tải lại trang để đồng bộ bản đồ, bảng và biểu đồ.';
    let banner=$('snapshot-warning');
    if(!banner){banner=document.createElement('p');banner.id='snapshot-warning';banner.className='canh';$('ung-dung').prepend(banner);}
    banner.textContent=message;
    $('detail-fields').innerHTML=`<p class="canh">${message}</p>`;
    $('vung-kinhte').innerHTML=`<p class="canh">${message}</p>`;
    if(economyChart){economyChart.dispose();economyChart=null;}
    if(banDo?.getLayer('anh-dem'))banDo.removeLayer('anh-dem');
    if(banDo?.getSource('anh-dem'))banDo.removeSource('anh-dem');
    throw new Error(message);
  }
  demoSnapshotInitialized=true;demoSnapshotId=id;
}
const CLASS_COLORS = ['#18233b','#5568a8','#56b9b0','#f6bc55','#ff765d'];

function contextPeriod(){
  return demoSelection.month ? `${demoSelection.year}-${String(demoSelection.month).padStart(2,'0')}` : String(demoSelection.year);
}
function syncContext(){
  if(!$('context-province').options.length) return;
  $('context-province').value = demoSelection.code || '';
  $('context-year').value = demoSelection.year;
  $('context-month').value = demoSelection.month;
  const name = danhSachTinh.find(p => p.province_code === demoSelection.code)?.province_name || 'Toàn quốc';
  $('context-summary').textContent = `${name} · ${contextPeriod()} · ${demoSelection.month ? 'theo tháng' : 'theo năm'}`;
}
function initDemoContext(){
  $('context-province').innerHTML = '<option value="">Toàn quốc</option>' + danhSachTinh.map(p =>
    `<option value="${p.province_code}">${thoat(p.province_name)}</option>`).join('');
  $('context-year').innerHTML = Array.from({length:22}, (_,i) => 2025-i).map(y => `<option>${y}</option>`).join('');
  $('context-month').innerHTML += Array.from({length:12}, (_,i) => `<option value="${i+1}">Tháng ${i+1}</option>`).join('');
  for(const id of ['context-province','context-year','context-month']) $(id).onchange = () =>
    applySharedContext($('context-province').value, Number($('context-year').value), Number($('context-month').value));
  $('layer-mode').onchange = renderDemoLayer;
  $('nut-tai-anh').onclick = downloadSelectedImage;
  syncContext();
}
async function applySharedContext(code, year, month, fromPanel=false){
  // Tạm dừng refresh trong các thay đổi nội bộ để tránh nhiều request dùng ngữ cảnh nửa cũ.
  const shared = ++sharedRequest;
  demoReady = false;
  demoSelection = {code:code || null, year:Number(year), month:Number(month)};
  $('chon-tinh').value = code || '';
  chonPhamVi(code);
  chon.tinh = new Set(code ? [code] : danhSachTinh.map(p => p.province_code));
  chon.moc = new Set([contextPeriod()]);
  if(!fromPanel && !month && year>=NAM_CO_THANG)
    for(let m=1;m<=12;m++)chon.moc.add(`${year}-${String(m).padStart(2,'0')}`);
  document.querySelectorAll('[data-tinh]').forEach(e => e.checked = chon.tinh.has(e.dataset.tinh));
  dongBoCay($('loc-chiso')); capNhatDem($('loc-chiso'));
  await napMoc(month ? 'thang' : 'nam', contextPeriod());
  if(shared !== sharedRequest) return;
  demoReady = true;
  syncContext();
  await Promise.all([napBang(), refreshDemo()]);
  if(!$('man-spatial').hidden)refreshSpatial();
}
async function adoptPanelContext(){
  const period = [...chon.moc][0].split('-');
  await applySharedContext([...chon.tinh][0], Number(period[0]), Number(period[1] || 0), true);
}
function demoParams(){
  const params=new URLSearchParams({province_code:demoSelection.code || '', nam:demoSelection.year, thang:demoSelection.month});
  if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
  return params;
}
function valueCell(value, reason, digits=2){
  if(value === null || value === undefined || !Number.isFinite(Number(value)))
    return `<span class="missing" title="${thoat(reason || 'Chưa có dữ liệu')}">— <small>${thoat(reason || 'Chưa có dữ liệu')}</small></span>`;
  return dinhDang(value, digits);
}
function assetLink(kind, label){
  const params = demoParams(); params.set('kind', kind);
  return `<a class="asset-link" href="/api/demo/image?${params}">${label}</a>`;
}
async function refreshDemo(){
  const request = ++demoRequest;
  const params = demoParams();
  dungManKinhTe();
  if(!demoSelection.code){
    demoDetails = null;
    $('detail-fields').innerHTML = '<p class="empty-state">Chọn một tỉnh để xem định danh, Raw và Processed ở mốc đang chọn. Bảng so sánh bên dưới vẫn hỗ trợ toàn quốc.</p>';
    $('class-summary').innerHTML = '';
    renderDemoLayer(); return;
  }
  $('detail-fields').innerHTML = '<p class="empty-state">Đang đọc dữ liệu tỉnh…</p>';
  try{
    const data = await layJSON('/api/demo/province?' + params);
    if(request !== demoRequest) return;
    checkDemoSnapshot(data);
    if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
    demoDetails = data;
    $('detail-fields').innerHTML = '';
    // Có thể có ảnh tỉnh đã đăng ký trước khi ghép COG toàn quốc.
    ++cardRequest;
    const field = name => data.fields.find(f => f.field === name)?.value;
    $('the-so').innerHTML = theSo('SOL', dinhDang(field('sol'),0) ?? '—', data.unit)
      + theSo('Diện tích sáng', dinhDang(field('lit_area_km2'),2) ?? '—', 'km²')
      + theSo('Mật độ', dinhDang(field('sol_density'),2) ?? '—', data.unit + '/km²');
    if(!cacMoc.length && data.processed_asset){
      $('chon-nam').innerHTML = `<option>${contextPeriod()} · ảnh tỉnh</option>`;
    }
    renderClassSummary(data);
    renderDemoLayer();
  }catch(error){
    if(request !== demoRequest) return;
    demoDetails = null;
    $('detail-fields').innerHTML = `<p class="canh thieu">Chưa đọc được dữ liệu tỉnh: ${thoat(error.message)}</p>`;
    $('class-summary').innerHTML = ''; renderDemoLayer();
  }
}
function renderClassSummary(data){
  if(data.class_status !== 'ready'){
    $('class-summary').innerHTML = `<p class="empty-state">${thoat(data.class_reason)}</p>`; return;
  }
  const reference = data.classes[0]?.status?.replace('empirical_reference_','');
  const methodNote = /^20\d{2}$/.test(reference) ? `Mốc 0,5 và 1,5 theo quy tắc dự án/Task 3; hai mốc còn lại là P50/P90 của pixel sáng năm ${reference}.` : 'Bộ phân lớp kiểm thử hoặc chưa có nhãn năm tham chiếu.';
  const s = data.class_summary;
  const fractional = s?.method_version === 'viirs_brightness_classes_v3_fractional';
  const params = new URLSearchParams({province_code:demoSelection.code,nam:demoSelection.year,thang:demoSelection.month});
  if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
  const audit = `<a class="asset-link" href="/api/demo/classes.csv?${params}">Tải CSV lớp sáng</a>`;
  $('class-summary').innerHTML = '<h3>Diện tích theo mức sáng</h3><table class="class-table"><thead><tr><th>Mức / ngưỡng</th><th>km²</th><th>% tỉnh</th></tr></thead><tbody>'
    + data.classes.map((c,i) => `<tr><td><i style="background:${CLASS_COLORS[i]}"></i>${CLASS_NAMES[i]}<small>${c.lower_bound} ≤ r ${c.upper_bound === null ? '' : '< '+c.upper_bound} ${thoat(c.unit)}</small></td><td>${valueCell(c.area_km2)}</td><td>${dinhDang(c.class_area_pct,2) ?? '—'}</td></tr>`).join('')
    + `</tbody></table>${audit}<p class="nho">${thoat(methodNote)} Ngưỡng giữ cố định giữa các năm. % tỉnh dùng diện tích tự nhiên làm mẫu số; NoData không thuộc lớp tối. ${fractional ? 'Diện tích tính theo phần giao pixel với tỉnh trong EPSG:6933.' : 'Kết quả cũ tính cả pixel giao biên; cần tính lại diện tích phần giao.'}</p>`;
}
function renderDemoLayer(){
  const mode = $('layer-mode').value;
  const data = demoDetails;
  let item = mode === 'processed' ? data?.processed_asset : mode === 'classes' ? data?.class_asset : data?.raw_asset;
  const unavailable=item?.available===false ? item.reason : '';
  if(item?.available===false)item=null;
  const legacyMoc = cacMoc.find(m => maMoc(m) === contextPeriod());
  if(mode === 'processed' && !item && legacyMoc && !unavailable && !demoSnapshotChanged) item = legacyMoc;
  const tileTemplate = data?.tiles || thongTinNen?.tiles;
  $('nut-tai-anh').disabled = demoSnapshotChanged || (!item && !(mode === 'processed' && legacyMoc && !unavailable));
  let reason = '';
  if(!demoSelection.code) reason = mode === 'processed' ? '' : 'Chọn một tỉnh để xem băng gốc hoặc năm mức sáng.';
  else if(!item) reason = unavailable || (mode === 'classes' ? (data?.class_reason || 'Chưa có kết quả phân lớp.') : 'Chưa đăng ký ảnh nguồn ở mốc này.');
  if(!tileTemplate) reason = 'Chưa có dịch vụ ô bản đồ; vẫn có thể xem bảng và tải GeoTIFF.';
  $('layer-status').textContent = reason || (mode === 'cf_cvg' ? 'Raw · số lượt quan sát sạch mây/pixel.' : mode === 'avg_rad' ? 'Raw · bức xạ của sản phẩm đầu vào.' : mode === 'classes' ? 'Processed · năm mức sáng, NoData được để trống.' : 'Processed · ảnh bức xạ đã xử lý.');
  if(!banDo || !banDo.isStyleLoaded()) return;
  if(!demoSelection.code && mode === 'processed') return; // Giữ ảnh toàn quốc của app cũ.
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  if(!item || !tileTemplate){ dongThangMau(); return; }
  let suffix = mode === 'classes' ? '&nodata=255&resampling=nearest&colormap=' + encodeURIComponent(JSON.stringify(Object.fromEntries(CLASS_COLORS.map((c,i) => [i,[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16),255]]))))
    : `&bidx=${mode === 'cf_cvg' ? 2 : 1}&rescale=0,${mode === 'cf_cvg' ? 20 : 60}&colormap_name=inferno&nodata=-9999`;
  const feature = ranhGioi?.features.find(f => String(f.properties.province_code).padStart(2,'0') === demoSelection.code);
  const source = {type:'raster',tileSize:256,tiles:[tileTemplate + encodeURIComponent(item.export_path || item.path) + suffix]};
  if(feature) source.bounds = bienDo(feature).flat();
  banDo.addSource('anh-dem', source);
  banDo.addLayer({id:'anh-dem',type:'raster',source:'anh-dem',paint:{'raster-opacity':1,'raster-resampling':mode === 'classes' ? 'nearest' : 'linear'}}, banDo.getLayer('mat-na-lop') ? 'mat-na-lop' : undefined);
  if(mode === 'classes'){
    $('thang-mau').style.display = '';
    $('thang-mau').innerHTML = '<span>Năm mức sáng · xem ngưỡng và diện tích ở cột trái</span>';
  }else{
    moThangMau({source: mode === 'cf_cvg' ? 'VIIRS' : data?.source || item.source});
    if(mode === 'cf_cvg') $('thang-mau').innerHTML = '<span>0 → 20 lượt · thang hiển thị, không phải giới hạn dữ liệu</span>';
  }
}
function downloadSelectedImage(){
  const mode = $('layer-mode').value;
  const kind = mode === 'classes' ? 'classes' : mode === 'processed' ? 'processed' : 'raw';
  const item = demoDetails?.[kind === 'raw' ? 'raw_asset' : kind === 'classes' ? 'class_asset' : 'processed_asset'];
  if(demoSnapshotChanged || item?.available===false)return;
  if(demoSelection.code && item){
    const params=demoParams(); params.set('kind',kind);
    window.location='/api/demo/image?'+params;
  }else if(mode === 'processed' && cacMoc.some(m => maMoc(m) === contextPeriod())){
    const params=new URLSearchParams({nam:demoSelection.year,thang:demoSelection.month});
    if(demoSelection.code)params.set('province_code',demoSelection.code);
    window.location='/api/anh-dem.tif?'+params;
  }
}

async function dungManKinhTe(){
  const request=++economyRequest,year=demoSelection.year,month=demoSelection.month;
  const params=new URLSearchParams({nam_tu:year,nam_den:year,price_basis:economyBasis,thang:month});
  if(demoSelection.code)params.set('province_code',demoSelection.code);
  $('loc-kinhte').innerHTML='<p>Dân số và hai loại GRDP chỉ hiển thị theo năm. Chọn tháng thì các giá trị này để trống.</p>';
  try{
    const data=await layJSON('/api/demo/economy?'+params);if(request!==economyRequest)return;
    if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
    const columns=[['province_name','Tỉnh'],['year','Năm'],['population','Dân số'],['grdp_so_sanh','GRDP so sánh (tỷ đồng)'],['grdp_hien_hanh','GRDP hiện hành (tỷ đồng)'],['sol','SOL'],['gdp_change_pct','Thay đổi GRDP (%)']];
    $('vung-kinhte').innerHTML='<h2>Dữ liệu kinh tế đêm</h2><div class="cuon"><table><thead><tr>'+columns.map(c=>`<th>${c[1]}</th>`).join('')+'</tr></thead><tbody>'+data.dong.map(r=>'<tr>'+columns.map(([f])=>`<td>${f==='province_name'?thoat(r[f]):dinhDang(r[f],2)??'—'}</td>`).join('')+'</tr>').join('')+'</tbody></table></div>'+`<a class="asset-link" href="/api/demo/economy.csv?${params}">Tải CSV</a>`;
  }catch(error){if(request===economyRequest)$('vung-kinhte').textContent=error.message;}
}
