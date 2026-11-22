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
    const identity = `<div class="data-identity"><b>${thoat(data.province.province_name)}</b>`
      + `<span>Mã thống kê ${data.province.province_code} · ${thoat(data.province.gid_1 || 'Chưa có mã GADM')}</span>`
      + `<span>${contextPeriod()} · ${thoat(data.source)}</span></div>`;
    const fields = stage => data.fields.filter(f => f.stage === stage).map(f => {
      let value = valueCell(f.value, f.reason);
      if(f.is_raster) value = f.available ? assetLink('raw','Tải GeoTIFF gốc hai băng') : valueCell(null,f.reason);
      return `<tr><td><code>${thoat(f.field)}</code><small>${thoat(f.name)}</small></td><td>${value}`
        + `${f.is_provisional ? '<span class="badge">Sơ bộ</span>' : ''}</td><td>${thoat(f.unit || '')}</td></tr>`;
    }).join('');
    const support = data.observation_support;
    const supportValue = key => valueCell(support?.[key] === '' ? null : support?.[key] == null ? null : Number(support[key]));
    const supportParams = new URLSearchParams({province_code:demoSelection.code,nam:demoSelection.year,thang:0,kind:'support'});
    if(demoSnapshotId)supportParams.set('expected_snapshot',demoSnapshotId);
    const recoveryNames = {NO_CLOUD_FREE_OBSERVATIONS:'Ảnh gốc không có quan sát sạch mây hợp lệ; giữ thiếu dữ liệu.',NO_VALID_RADIANCE_DESPITE_CF:'Có thông tin quan sát nhưng bức xạ gốc không hợp lệ; chưa phục hồi được.',REPAIRED_FILTER_MISMATCH:'Đã sửa ảnh lọc từ quan sát hợp lệ trong ảnh gốc.',MATCHES_RAW_FILTER_RULE:'Ảnh lọc khớp quy tắc và quan sát gốc.',MISSING_RAW_OR_FILTERED_MONTHS:'Thiếu ảnh gốc hoặc ảnh tháng để kiểm tra đầy đủ năm.',GRID_MISMATCH_REQUIRES_REVIEW:'Lưới ảnh gốc và ảnh lọc khác nhau; cần đối chiếu trước khi sửa.',FILTER_RULE_UNVERIFIED:'Chưa xác minh quy tắc lọc; giữ nguyên dữ liệu.',SOURCE_READ_ERROR:'Chưa đọc được ảnh nguồn; cần kiểm tra đường dẫn/file.'};
    recoveryNames.MISSING_CF_COVERAGE = 'Thông tin số lượt quan sát trong ảnh gốc không hợp lệ; chưa thể xác nhận quan sát.';
    const recoveryInfo = data.recovery_audit ? `<p class="nho">Kiểm tra ảnh tháng: ${thoat(recoveryNames[data.recovery_audit.diagnosis] || data.recovery_audit.diagnosis)}</p>` : '';
    const supportInfo = recoveryInfo + (support ? `<p class="nho">Ảnh năm ${data.year}: số tháng hợp lệ trên pixel có quan sát từ ${supportValue('valid_month_min')} đến ${supportValue('valid_month_max')}, trung bình ${supportValue('valid_month_mean')}. Diện tích không có tháng nào hợp lệ: ${supportValue('area_without_observations_km2')} km². Có file tháng không đồng nghĩa có quan sát ở mọi pixel.</p>${data.support_asset?.available ? `<a class="asset-link" href="/api/demo/image?${supportParams}">Tải bản đồ số tháng hợp lệ trong năm</a>` : '<p class="nho">Bản đồ số tháng hợp lệ hiện không sẵn có.</p>'}` : '');
    const group = stage => `<section class="data-group ${stage.toLowerCase()}"><h2>${stage === 'Raw' ? '01 · Raw — dữ liệu đầu vào' : '02 · Processed — kết quả tính toán'}</h2>`
      + `<div class="cuon"><table><thead><tr><th>Trường dữ liệu</th><th>Giá trị / dữ liệu nguồn</th><th>Đơn vị</th></tr></thead><tbody>${fields(stage)}</tbody></table></div>${stage === 'Processed' ? supportInfo : ''}</section>`;
    $('detail-fields').innerHTML = identity + (data.is_simulated ? '<p class="canh thieu">SỐ LIỆU GIẢ LẬP — chỉ kiểm thử giao diện.</p>' : '')
      + `<p class="nho">Bộ dữ liệu: ${thoat(data.provenance?.dataset_id?.slice(0,12) || 'chưa có mã snapshot')} · phiên bản thống kê ${data.provenance?.stats_version ?? 'chưa xác minh'}.</p>`
      + (data.provenance?.reason ? `<p class="canh">${thoat(data.provenance.reason)} Các số đã lưu vẫn được giữ để tra cứu.</p>` : '')
      + group('Raw') + group('Processed')
      + `<a class="asset-link" href="/api/demo/province.csv?${params}">Tải CSV chỉ số · cùng tỉnh/mốc</a>`;
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
  const audit = s ? `<p class="nho">Diện tích tự nhiên: ${valueCell(s.area_km2)} km².<br>Diện tích có dữ liệu: ${valueCell(s.valid_area_km2)} km² · độ phủ ${valueCell(s.valid_area_pct)}%.<br>Pixel hợp lệ: ${s.valid_pixels}; NoData: ${s.nodata_pixels}.<br>Kiểm chứng: ${s.validation_status === 'passed' ? 'đạt' : 'không có pixel hợp lệ'}; sai lệch tổng lớp ${valueCell(s.area_balance_error_km2)} km².</p>`
    + ((s.valid_area_pct ?? 0) > 100 ? '<p class="canh-nho">Độ phủ vượt 100%: cần đối chiếu mask và diện tích tỉnh. Tính cả pixel giao biên cũng có thể làm độ phủ vượt 100%; chưa hiệu chỉnh phần giao ranh giới.</p>' : '')
    + `<a class="asset-link" href="/api/demo/classes.csv?${params}">Tải CSV lớp sáng · tỉnh/mốc đang chọn</a>`
    : '<p class="nho">Chưa có báo cáo kiểm chứng phần D; cần chạy bộ phân lớp để bổ sung tỷ lệ và độ phủ.</p>';
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
  const request = ++economyRequest;
  const year = demoSelection.year;
  const params = new URLSearchParams({nam_tu:year,nam_den:year,price_basis:economyBasis});
  if(demoSelection.code) params.set('province_code',demoSelection.code);
  const heading = `<label for="economy-basis">Cơ sở giá GRDP</label><select id="economy-basis">`
    + `<option value="so_sanh">Giá so sánh · chính thức</option><option value="hien_hanh">Giá hiện hành · đối chiếu</option><option value="compare">Đối chiếu hai loại giá</option></select>`;
  $('loc-kinhte').innerHTML = heading + '<p class="canh-nho">Dùng tỉnh và năm ở thanh phạm vi chung. GRDP theo năm; chọn tháng không biến GRDP thành số tháng.</p>'
    + '<p class="canh-nho">Hai mô hình dùng cùng mẫu có đủ hai loại GRDP và SOL dương. Chọn Toàn quốc để phân tích cả 63 tỉnh.</p>';
  $('economy-basis').value = economyBasis;
  $('economy-basis').onchange = e => { economyBasis=e.target.value; dungManKinhTe(); };
  $('vung-kinhte').innerHTML = '<p class="empty-state">Đang đọc số liệu kinh tế…</p>';
  try{
    const data = await layJSON('/api/demo/economy?' + params);
    if(request !== economyRequest) return;
    checkDemoSnapshot(data);
    if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
    const basis = economyBasis === 'hien_hanh' ? 'hien_hanh' : 'so_sanh';
    const fit = data.hoi_quy[basis];
    const fitCard = (key,label) => { const h=data.hoi_quy[key]; return `<article class="fit-card"><h3>${label}</h3><p>β ${dinhDang(h.beta,3) ?? '—'} · R² ${dinhDang(h.r2,3) ?? '—'} · n ${h.n}</p><small>${h.beta === null ? 'Chưa đủ quan sát hợp lệ để ước lượng.' : 'ln(GRDP) = α + β·ln(SOL)'}</small></article>`; };
    const rawHeader = economyBasis === 'compare' ? '<th>GRDP so sánh</th><th>GRDP hiện hành</th>' : `<th>GRDP ${basis === 'so_sanh' ? 'so sánh' : 'hiện hành'}</th>`;
    $('vung-kinhte').innerHTML = `<div class="data-identity"><b>${demoSelection.code ? thoat(danhSachTinh.find(p=>p.province_code===demoSelection.code)?.province_name || '') : '63 tỉnh trước sáp nhập'} · ${year}</b><span>GRDP theo năm · ${data.paired_count} quan sát chung đủ điều kiện</span></div>`
      + `<p class="nho">Snapshot: ${thoat(data.snapshot_id?.slice(0,12) || 'chưa xác minh')}.</p>`
      + data.canh_bao.map(t=>`<p class="canh">${thoat(t)}</p>`).join('')
      + `<section class="data-group raw"><h2>01 · Raw — dân số và GRDP</h2><p class="nho">Đơn vị GRDP: tỷ đồng với bộ cô cung cấp; giá so sánh năm gốc 2010. Năm 2024 sơ bộ được đánh dấu theo dữ liệu.</p>`
      + `<div class="cuon"><table id="economy-raw"><thead><tr><th>Tỉnh</th><th>Năm</th><th>Dân số</th>${rawHeader}<th>Chất lượng</th></tr></thead><tbody>`
      + data.dong.map(r=>`<tr><td>${thoat(r.province_name)}</td><td>${r.year}</td><td>${valueCell(r.population,'Chưa có dân số',0)}</td>`
        + (economyBasis === 'compare' ? `<td>${valueCell(r.grdp_so_sanh,'Thiếu GRDP giá so sánh',0)}</td><td>${valueCell(r.grdp_hien_hanh,'Thiếu GRDP giá hiện hành',0)}</td>` : `<td>${valueCell(r.grdp,'Thiếu GRDP ở cơ sở giá đang chọn',0)}</td>`)
        + `<td>${r.is_provisional ? '<span class="badge">Sơ bộ</span>' : ''}${r.quality_flags ? `<small title="${thoat(r.quality_flags)}">Cần đối chiếu nguồn</small>` : ''}${r.image_quality_flags ? `<small title="${thoat(r.image_quality_flags)}">Cần rà soát chất lượng ảnh</small>` : ''}${r.is_simulated ? '<b>SỐ GIẢ LẬP</b>' : ''}</td></tr>`).join('')
      + `</tbody></table></div>${!data.dong.length ? '<p class="empty-state">Chưa nạp GRDP cho phạm vi này.</p>' : ''}</section>`
      + `<section class="data-group processed"><h2>02 · Processed — ánh sáng và quan hệ với GRDP</h2><p class="nho">${economyBasis === 'compare' ? 'Các cột dẫn xuất và biểu đồ dùng giá so sánh; hai ô hồi quy đối chiếu riêng hai loại giá trên cùng mẫu.' : 'Các cột dẫn xuất và biểu đồ theo cơ sở giá đang chọn.'}</p>`
      + `<div class="fit-grid">${economyBasis === 'compare' ? fitCard('so_sanh','Giá so sánh')+fitCard('hien_hanh','Giá hiện hành') : fitCard(basis,basis === 'so_sanh'?'Giá so sánh':'Giá hiện hành')}</div>`
      + `<div class="cuon"><table><thead><tr><th>Tỉnh</th><th>Năm</th><th>SOL</th><th>SOL/người</th><th>Δ GRDP (%)</th><th>Δ sáng / Δ GRDP</th><th>GRDP ước lượng</th><th>Mẫu chung</th></tr></thead><tbody>`
      + data.dong.map(r=>`<tr><td>${thoat(r.province_name)}</td><td>${r.year}</td><td>${valueCell(r.sol,r.missing_reason || 'Chưa có chỉ số ánh sáng',0)}</td><td>${valueCell(r.sol_per_capita,'Thiếu dân số hoặc SOL',4)}</td><td>${valueCell(r.gdp_change_pct,'Thiếu năm tham chiếu hoặc GRDP không dương',2)}</td><td>${valueCell(r.light_gdp_elasticity,'Chưa nạp kết quả tỷ số tăng trưởng',3)}</td><td>${valueCell(r.predicted_gdp,'Chưa nạp kết quả ước lượng',0)}${r.model_n ? `<small>Mẫu ${thoat(r.model_training_period)} · n=${r.model_n}; biểu đồ bên trên dùng phạm vi đang chọn.</small>` : ''}</td><td>${r.paired ? 'Có' : 'Chưa đủ dữ liệu'}</td></tr>`).join('')
      + '</tbody></table></div><div class="bieu-do" id="economy-scatter"></div></section>'
      + `<a class="asset-link" href="/api/demo/economy.csv?${params}">Tải CSV · cùng tỉnh/năm/cơ sở giá</a>`;
    if(economyChart) economyChart.dispose();
    if(typeof echarts !== 'undefined'){
      economyChart = echarts.init($('economy-scatter'));
      const points = data.dong.filter(r=>r.paired).map(r=>[Math.log(r.sol),Math.log(r['grdp_'+basis])]);
      const xs=points.map(p=>p[0]);
      const regression = fit.beta !== null && xs.length ? [Math.min(...xs),Math.max(...xs)].map(x=>[x,fit.alpha+fit.beta*x]) : [];
      economyChart.setOption({textStyle:{color:'#8b97b0'},tooltip:{trigger:'item'},xAxis:{type:'value',name:'ln(SOL)',scale:true},yAxis:{type:'value',name:'ln(GRDP)',scale:true},series:[{type:'scatter',data:points},{type:'line',data:regression,symbol:'none'}]});
    }
  }catch(error){
    if(request === economyRequest) $('vung-kinhte').innerHTML = `<p class="canh thieu">Không đọc được số liệu kinh tế: ${thoat(error.message)}</p>`;
  }
}
