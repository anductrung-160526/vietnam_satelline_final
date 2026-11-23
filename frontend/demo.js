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
    $('economy-results').innerHTML=`<p class="canh">${message}</p>`;
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
  if(!$('man-kinhte').hidden)dungManKinhTe();
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
  const methodNote = /^20\d{2}$/.test(reference) ? `Mốc 0,50 và 1,50 theo quy tắc dự án/Task 3; hai mốc còn lại là P50/P90 của pixel sáng năm ${reference}.` : 'Bộ phân lớp kiểm thử hoặc chưa có nhãn năm tham chiếu.';
  const s = data.class_summary;
  const fractional = s?.method_version === 'viirs_brightness_classes_v3_fractional';
  const params = new URLSearchParams({province_code:demoSelection.code,nam:demoSelection.year,thang:demoSelection.month});
  if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
  const audit = `<a class="asset-link" href="/api/demo/classes.csv?${params}">Tải CSV lớp sáng</a>`;
  $('class-summary').innerHTML = '<h3>Diện tích theo mức sáng</h3><table class="class-table"><thead><tr><th>Mức / ngưỡng</th><th>km²</th><th>% tỉnh</th></tr></thead><tbody>'
    + data.classes.map((c,i) => `<tr><td><i style="background:${CLASS_COLORS[i]}"></i>${CLASS_NAMES[i]}<small>${dinhDang(c.lower_bound,2)} ≤ r ${c.upper_bound === null ? '' : '< '+dinhDang(c.upper_bound,2)} ${thoat(c.unit)}</small></td><td>${valueCell(c.area_km2)}</td><td>${dinhDang(c.class_area_pct,2) ?? '—'}</td></tr>`).join('')
    + `</tbody></table>${audit}<p class="nho">${thoat(methodNote)} Ngưỡng giữ cố định giữa các năm. % tỉnh dùng diện tích tự nhiên làm mẫu số; NoData không thuộc lớp tối. ${fractional ? 'Diện tích tính theo phần giao pixel với tỉnh trong EPSG:6933.' : 'Kết quả cũ tính cả pixel giao biên; cần tính lại diện tích phần giao.'}</p>`;
}
function renderDemoLayer(){
  const mode = $('layer-mode').value;
  const data = demoDetails;
  let item = mode === 'classes' ? data?.class_asset : data?.processed_asset;
  const unavailable=item?.available===false ? item.reason : '';
  if(item?.available===false)item=null;
  const legacyMoc = cacMoc.find(m => maMoc(m) === contextPeriod());
  if(mode === 'processed' && !item && legacyMoc && !unavailable && !demoSnapshotChanged) item = legacyMoc;
  const tileTemplate = data?.tiles || thongTinNen?.tiles;
  $('nut-tai-anh').disabled = demoSnapshotChanged || (!item && !(mode === 'processed' && legacyMoc && !unavailable));
  let reason = '';
  if(!demoSelection.code) reason = mode === 'processed' ? '' : 'Chọn một tỉnh để xem phân vùng cường độ ánh sáng.';
  else if(!item) reason = unavailable || (mode === 'classes' ? (data?.class_reason || 'Chưa có kết quả phân lớp.') : 'Chưa đăng ký ảnh nguồn ở mốc này.');
  if(!tileTemplate) reason = 'Chưa có dịch vụ ô bản đồ; vẫn có thể xem bảng và tải GeoTIFF.';
  $('layer-status').textContent = reason || (mode === 'classes' ? 'Phân vùng theo ngưỡng cường độ ánh sáng; vùng không có dữ liệu được để trống.' : 'Phân bố bức xạ ánh sáng ban đêm.');
  if(!banDo || !banDo.isStyleLoaded()) return;
  if(!demoSelection.code && mode === 'processed') return; // Giữ ảnh toàn quốc của app cũ.
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  if(!item || !tileTemplate){ dongThangMau(); return; }
  let suffix = mode === 'classes' ? '&nodata=255&resampling=nearest&colormap=' + encodeURIComponent(JSON.stringify(Object.fromEntries(CLASS_COLORS.map((c,i) => [i,[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16),255]]))))
    : '&bidx=1&rescale=0,60&colormap_name=inferno&nodata=-9999';
  const feature = ranhGioi?.features.find(f => String(f.properties.province_code).padStart(2,'0') === demoSelection.code);
  const source = {type:'raster',tileSize:256,tiles:[tileTemplate + encodeURIComponent(item.export_path || item.path) + suffix]};
  if(feature) source.bounds = bienDo(feature).flat();
  banDo.addSource('anh-dem', source);
  banDo.addLayer({id:'anh-dem',type:'raster',source:'anh-dem',paint:{'raster-opacity':1,'raster-resampling':mode === 'classes' ? 'nearest' : 'linear'}}, banDo.getLayer('mat-na-lop') ? 'mat-na-lop' : undefined);
  if(mode === 'classes'){
    $('thang-mau').style.display = '';
    $('thang-mau').innerHTML = '<span>Phân vùng cường độ ánh sáng · ngưỡng và diện tích ở cột trái</span>';
  }else{
    moThangMau({source: data?.source || item.source});
  }
}
function downloadSelectedImage(){
  const mode = $('layer-mode').value;
  const kind = mode === 'classes' ? 'classes' : 'processed';
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

let economyInitialized=false;
function economyRange(){return [Number($('economy-start').value),Number($('economy-end').value)];}
function initEconomyPanel(){
  if(economyInitialized)return;
  $('loc-kinhte').innerHTML='<label for="economy-start">Từ năm</label><select id="economy-start"></select>'
    +'<label for="economy-end">Đến năm</label><select id="economy-end"></select>'
    +'<label for="economy-province">Phạm vi phân tích</label><select id="economy-province"><option value="">Toàn bộ tỉnh</option></select>'
    +'<label for="economy-basis">Cơ sở giá GRDP</label><select id="economy-basis"><option value="so_sanh">Giá so sánh</option><option value="hien_hanh">Giá hiện hành</option><option value="compare">Đối chiếu hai cơ sở giá</option></select>'
    +'<p class="canh-nho">Bảng và hồi quy dùng chung dữ liệu năm trong phạm vi đã chọn. Giá so sánh là cơ sở phân tích chính.</p>';
  for(const id of ['economy-start','economy-end'])$(id).innerHTML=Array.from({length:22},(_,i)=>2004+i).map(y=>`<option>${y}</option>`).join('');
  $('economy-start').value=2020;$('economy-end').value=2024;
  $('economy-province').innerHTML+=danhSachTinh.map(p=>`<option value="${p.province_code}">${thoat(p.province_name)}</option>`).join('');
  for(const id of ['economy-start','economy-end','economy-province','economy-basis'])$(id).onchange=dungManKinhTe;
  $('economy-moran').ontoggle=()=>{if($('economy-moran').open)refreshSpatial();};
  economyInitialized=true;
}
async function dungManKinhTe(){
  initEconomyPanel();const request=++economyRequest,[first,last]=economyRange();
  const code=$('economy-province').value,basis=$('economy-basis').value;
  economyBasis=basis;
  if(economyChart){economyChart.dispose();economyChart=null;}
  $('economy-results').innerHTML='<p>Đang đọc dữ liệu kinh tế đêm…</p>';
  invalidateSpatial();
  if(first>last){$('economy-results').textContent='Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.';return;}
  const params=new URLSearchParams({nam_tu:first,nam_den:last,price_basis:basis,thang:0});
  if(code)params.set('province_code',code);
  try{
    const data=await layJSON('/api/demo/economy?'+params);if(request!==economyRequest)return;
    if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
    const selected=basis==='hien_hanh'?'hien_hanh':'so_sanh';
    const bases=basis==='compare'?['so_sanh','hien_hanh']:[selected];
    const label=b=>b==='so_sanh'?'Giá so sánh':'Giá hiện hành';
    const scope=code ? danhSachTinh.find(p=>p.province_code===code)?.province_name || code : 'Toàn bộ tỉnh';
    const columns=[['province_name','Tỉnh'],['year','Năm'],['grdp_so_sanh','GRDP so sánh'],['grdp_hien_hanh','GRDP hiện hành'],['sol','SOL'],['gdp_change_pct','Δ GRDP '+(selected==='so_sanh'?'so sánh':'hiện hành')+' (%)']];
    const cell=(r,f)=>f==='province_name'?thoat(r[f]):f==='year'?String(r[f]):dinhDang(r[f],2)??'—';
    const fitCard=b=>{const fit=data.hoi_quy[b];return `<article class="fit-card"><h3>${label(b)}</h3>`
      +`<p>β = ${dinhDang(fit.beta,4)??'—'} · R² = ${dinhDang(fit.r2,4)??'—'} · n = ${data.paired_count}</p>`
      +`<small>${fit.beta==null ? 'Chưa đủ quan sát dương hoặc phương sai để khớp hồi quy.' : 'ln(GRDP) = '+dinhDang(fit.alpha,4)+' + ('+dinhDang(fit.beta,4)+') × ln(SOL)'}</small></article>`;};
    $('economy-results').innerHTML=`<h2>Ánh sáng ban đêm và GRDP</h2><p>${thoat(scope)} · ${first}–${last} · dữ liệu năm. GRDP: tỷ đồng; SOL: thang đo theo nguồn ảnh.</p>`
      +(!data.dong.some(r=>r.grdp_so_sanh!=null || r.grdp_hien_hanh!=null)?'<p class="canh">Chưa tìm thấy GRDP năm trong database đang mở; kiểm tra bộ dữ liệu đã nạp.</p>':'')
      +`<div class="fit-grid">${bases.map(fitCard).join('')}</div>`
      +'<div class="economy-layout"><section><h3>Bảng dữ liệu</h3><div class="economy-table-scroll"><table id="economy-data-table"><thead><tr>'
      +columns.map(([f,name])=>`<th>${name}</th>`).join('')+'</tr></thead><tbody>'
      +data.dong.map(r=>'<tr>'+columns.map(([f])=>`<td>${cell(r,f)}</td>`).join('')+'</tr>').join('')+'</tbody></table></div>'
      +`<p class="nho">${data.dong.length} dòng; ${data.paired_count} cặp đủ hai giá GRDP và SOL dương, cùng nguồn VIIRS, dùng cho hồi quy. Ô thiếu giữ trống.</p>`
      +`<a class="asset-link" href="/api/demo/economy.csv?${params}">Tải CSV theo bộ lọc</a></section>`
      +'<section><h3>Quan hệ ánh sáng – GRDP</h3><div id="economy-scatter" class="economy-scatter"></div><p class="nho">Các điểm và đường hồi quy dùng cùng mẫu đủ điều kiện của bảng. Hồi quy log–log mô tả mối liên hệ, không chứng minh nhân quả.</p></section></div>'
      +(basis!=='so_sanh'?'<p class="nho">Giá hiện hành dùng đối chiếu, có ảnh hưởng biến động giá.</p>':'');
    if(typeof echarts!=='undefined'){
      economyChart=echarts.init($('economy-scatter'));
      const colors=['#ffc857','#6aa9ff'],series=[];
      bases.forEach((b,i)=>{
        const fit=data.hoi_quy[b];const points=data.dong.filter(r=>r.paired && r.sol>0 && r['grdp_'+b]>0).map(r=>({value:[Math.log(r.sol),Math.log(r['grdp_'+b])],province:r.province_name,year:r.year}));
        series.push({name:label(b),type:'scatter',data:points,itemStyle:{color:colors[i]},symbolSize:7});
        if(fit.beta!=null && points.length){const xs=points.map(p=>p.value[0]),ends=[Math.min(...xs),Math.max(...xs)];series.push({name:'Hồi quy · '+label(b),type:'line',data:ends.map(x=>[x,fit.alpha+fit.beta*x]),symbol:'none',itemStyle:{color:colors[i]},lineStyle:{color:colors[i],width:2},silent:true});}
      });
      economyChart.setOption({textStyle:{color:'#9aa8be'},legend:{textStyle:{color:'#9aa8be'}},grid:{left:65,right:30,top:65,bottom:55},tooltip:{trigger:'item',formatter:p=>{const r=p.data;return r.province ? `${thoat(r.province)} · ${r.year}<br>ln(SOL): ${dinhDang(r.value[0],3)}<br>ln(GRDP): ${dinhDang(r.value[1],3)}`:'';}},xAxis:{type:'value',name:'ln(SOL)',nameLocation:'middle',nameGap:30,scale:true},yAxis:{type:'value',name:'ln(GRDP)',scale:true},series});
      if(!data.paired_count)$('economy-scatter').insertAdjacentHTML('afterend','<p class="canh">Không có mẫu hợp lệ để vẽ biểu đồ. Chọn khoảng năm hoặc phạm vi rộng hơn khi có dữ liệu.</p>');
      requestAnimationFrame(()=>economyChart?.resize());
    }
    if($('economy-moran').open)refreshSpatial();
  }catch(error){if(request===economyRequest)$('economy-results').textContent=error.message;}
}
