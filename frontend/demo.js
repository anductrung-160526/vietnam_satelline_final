"use strict";
// Phần B: một ngữ cảnh tỉnh/năm/tháng, cùng kết quả cho bản đồ, Raw và Processed.
let demoSelection = {code:'01', year:2024, month:0};
let demoReady = false;
let sharedRequest = 0;
let demoRequest = 0;
let economyRequest = 0;
let economyChart = null;
let economyChartRenderer = null;
let demoDetails = null;
let economyBasis = 'so_sanh';
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
    $('economy-data-results').innerHTML='';$('economy-analysis-results').innerHTML='';
    economyChartRenderer=null;
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
    $('the-so').innerHTML = theSo('Quy mô kinh tế đêm theo ánh sáng (SOL)', dinhDang(field('sol'),0) ?? '—', data.unit)
      + theSo('Diện tích được chiếu sáng', dinhDang(field('lit_area_km2'),2) ?? '—', 'km²')
      + theSo('Mật độ kinh tế đêm theo ánh sáng', dinhDang(field('sol_density'),2) ?? '—', data.unit + '/km²');
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
  if(data.source!=='VIIRS'){$('class-summary').textContent='Bộ phân lớp cường độ bức xạ này chỉ áp dụng ảnh VIIRS.';return;}
  const config=data.classification_config;
  if(!config){$('class-summary').textContent='Cần tải lại ứng dụng để đồng bộ bộ ngưỡng phân lớp.';return;}
  const ready=data.classification_current && data.class_status==='ready';
  const rows=ready?data.classes:config.classes.map(c=>({...c,area_km2:null,class_area_pct:null,unit:config.unit}));
  const params = new URLSearchParams({province_code:demoSelection.code,nam:demoSelection.year,thang:demoSelection.month});
  if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
  const audit=ready?`<a class="asset-link" href="/api/demo/classes.csv?${params}">Tải CSV lớp sáng</a>`:'';
  $('class-summary').innerHTML='<h3>Diện tích theo cường độ bức xạ</h3>'
    +(!ready?'<p class="canh">Chưa có kết quả đã kiểm chứng theo bộ ngưỡng 0,50 / 2,00 / 10,00 / 20,00 cho ảnh này. Diện tích để trống đến khi cập nhật phân lớp.</p>':'')
    +'<table class="class-table"><thead><tr><th>Mức / ngưỡng</th><th>km²</th><th>% tỉnh</th></tr></thead><tbody>'
    +rows.map((c,i)=>`<tr><td><i style="background:${CLASS_COLORS[i]}"></i>${thoat(config.classes[i].name)}<small>${dinhDang(c.lower_bound,2)} ≤ r ${c.upper_bound===null?'':'< '+dinhDang(c.upper_bound,2)} ${thoat(c.unit)}</small></td><td>${valueCell(c.area_km2)}</td><td>${dinhDang(c.class_area_pct,2)??'—'}</td></tr>`).join('')
    +`</tbody></table>${audit}<details class="classification-method"><summary>Căn cứ phân lớp</summary><p>${config.sources.map(s=>`<a href="${thoat(s.url)}" target="_blank" rel="noopener noreferrer">${thoat(s.title)}</a>`).join('<br>')}</p><p class="nho">${thoat(config.interpretation)} Ngưỡng giữ cố định giữa các năm; NoData không thuộc lớp thấp nhất. Diện tích tính theo phần giao pixel–tỉnh. Ngưỡng tính pixel sáng 1,50 là tham số riêng, không phải mốc phân lớp này.</p></details>`;
}
let demoLayerScheduled=false;
function renderDemoLayer(){
  const mode = $('layer-mode').value;
  const data = demoDetails;
  let item = mode === 'classes' ? data?.class_asset : data?.processed_asset;
  if(mode==='classes' && !data?.classification_current)item=null;
  const unavailable=item?.available===false ? item.reason : '';
  if(item?.available===false)item=null;
  const legacyMoc = cacMoc.find(m => maMoc(m) === contextPeriod());
  if(mode === 'processed' && !item && legacyMoc && !unavailable && !demoSnapshotChanged) item = legacyMoc;
  const tileTemplate = data?.tiles || thongTinNen?.tiles;
  $('nut-tai-anh').disabled = demoSnapshotChanged || (!item && !(mode === 'processed' && legacyMoc && !unavailable));
  let reason = '';
  if(!demoSelection.code) reason = mode === 'processed' ? '' : 'Chọn một tỉnh để xem phân vùng cường độ ánh sáng.';
  else if(!item) reason = unavailable || (mode === 'classes' ? 'Chưa có phân lớp đã kiểm chứng theo bộ ngưỡng tài liệu cho ảnh này.' : 'Chưa đăng ký ảnh nguồn ở mốc này.');
  if(!tileTemplate) reason = 'Chưa có dịch vụ ô bản đồ; vẫn có thể xem bảng và tải GeoTIFF.';
  $('layer-status').textContent = reason || (mode === 'classes' ? 'Phân vùng theo ngưỡng cường độ ánh sáng; vùng không có dữ liệu được để trống.' : 'Phân bố bức xạ ánh sáng ban đêm.');
  if(mode==='classes'){
    if(item && tileTemplate)moThangMau({source:data.source});else dongThangMau();
  }
  if(!banDo)return;
  if(!banDo.isStyleLoaded()){
    if(!demoLayerScheduled){demoLayerScheduled=true;banDo.once('idle',()=>{demoLayerScheduled=false;renderDemoLayer();});}
    return;
  }
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
  moThangMau({source: data?.source || item.source});
}
function downloadSelectedImage(){
  const mode = $('layer-mode').value;
  if(mode==='classes' && !demoDetails?.classification_current)return;
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
let economySelectedFields=null;
let economyView='data';
function selectEconomyView(view){
  economyView=view;
  for(const name of ['data','analysis']){
    const selected=name===view;
    const button=$(`economy-${name}-tab`);
    button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;
    $(`economy-${name}-panel`).hidden=!selected;
  }
  $('economy-data-controls').hidden=view!=='data';
  if(view==='analysis'){
    if(!economyChart && economyChartRenderer)economyChartRenderer();
    requestAnimationFrame(()=>economyChart?.resize());
    if(!$('spatial-results').textContent && $('economy-analysis-results').textContent)refreshSpatial();
  }
}
function economyRange(){return [Number($('economy-start').value),Number($('economy-end').value)];}
function initEconomyPanel(){
  if(economyInitialized)return;
  $('loc-kinhte').innerHTML='<label for="economy-start">Từ năm</label><select id="economy-start"></select>'
    +'<label for="economy-end">Đến năm</label><select id="economy-end"></select>'
    +'<label for="economy-province">Phạm vi phân tích</label><select id="economy-province"><option value="">Toàn bộ tỉnh</option></select>'
    +'<label for="economy-basis">Cơ sở giá GRDP</label><select id="economy-basis"><option value="so_sanh">Giá so sánh</option><option value="hien_hanh">Giá hiện hành</option><option value="compare">Đối chiếu hai cơ sở giá</option></select>'
    +'<div id="economy-data-controls"><label for="economy-frequency">Tần suất bảng dữ liệu</label><select id="economy-frequency"><option value="annual">Theo năm</option><option value="monthly">Theo tháng</option><option value="both">Năm và tháng</option></select><div id="economy-indicators"></div></div>'
    +'<p class="canh-nho">Hồi quy sử dụng dữ liệu năm trong phạm vi đã chọn; GRDP ở dòng tháng để trống. Giá so sánh là cơ sở phân tích chính.</p>';
  for(const id of ['economy-start','economy-end'])$(id).innerHTML=Array.from({length:22},(_,i)=>2004+i).map(y=>`<option>${y}</option>`).join('');
  $('economy-start').value=2020;$('economy-end').value=2024;
  $('economy-province').innerHTML+=danhSachTinh.map(p=>`<option value="${p.province_code}">${thoat(p.province_name)}</option>`).join('');
  for(const id of ['economy-start','economy-end','economy-province','economy-basis','economy-frequency'])$(id).onchange=dungManKinhTe;
  const tabs=[...document.querySelectorAll('[data-economy-view]')];
  for(const [index,button] of tabs.entries()){
    button.onclick=()=>selectEconomyView(button.dataset.economyView);
    button.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      tabs[next].click();tabs[next].focus();
    };
  }
  economyInitialized=true;
}
async function dungManKinhTe(){
  initEconomyPanel();const request=++economyRequest,[first,last]=economyRange();
  const code=$('economy-province').value,basis=$('economy-basis').value;
  economyBasis=basis;
  if(economyChart){economyChart.dispose();economyChart=null;}
  economyChartRenderer=null;
  $('economy-data-results').innerHTML='';$('economy-analysis-results').innerHTML='';
  $('economy-results').innerHTML='<p>Đang đọc dữ liệu kinh tế đêm…</p>';
  invalidateSpatial();
  if(first>last){$('economy-results').textContent='Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.';return;}
  const params=new URLSearchParams({nam_tu:first,nam_den:last,price_basis:basis,thang:0,view_frequency:$('economy-frequency').value});
  if(code)params.set('province_code',code);
  try{
    const data=await layJSON('/api/demo/economy?'+params);if(request!==economyRequest)return;
    if(demoSnapshotId)params.set('expected_snapshot',demoSnapshotId);
    const selected=basis==='hien_hanh'?'hien_hanh':'so_sanh';
    const bases=basis==='compare'?['so_sanh','hien_hanh']:[selected];
    const label=b=>b==='so_sanh'?'Giá so sánh':'Giá hiện hành';
    const scope=code ? danhSachTinh.find(p=>p.province_code===code)?.province_name || code : 'Toàn bộ tỉnh';
    // GRDP ước lượng vẫn được tính và xuất CSV, nhưng không nằm trong bảng/bộ chọn cột.
    const allColumns=data.columns.filter(c=>c.field!=='predicted_gdp');
    const regression=data.regression_rows;
    if(economySelectedFields===null)economySelectedFields=new Set(allColumns.map(c=>c.field));
    const visible=allColumns.filter(c=>economySelectedFields.has(c.field));
    const families=[];
    for(const stage of ['Raw','Processed']){
      const group=allColumns.filter(c=>c.stage===stage);
      families.push(`<h3 class="indicator-section">${stage==='Raw'?'Dữ liệu đầu vào · Raw':'Chỉ số tính toán · Processed'}</h3><ul class="ds">`+group.map(c=>`<li class="indicator-row"><label><input type="checkbox" data-economy-field="${c.field}"${economySelectedFields.has(c.field)?' checked':''}><span>${thoat(c.name)}</span></label>${indicatorInfoButton(c)}</li>`).join('')+'</ul>');
    }
    $('economy-indicators').innerHTML=families.join('');
    $('economy-indicators').onchange=event=>{const field=event.target.dataset.economyField;if(!field)return;event.target.checked?economySelectedFields.add(field):economySelectedFields.delete(field);dungManKinhTe();};
    if(visible.length)params.set('fields',data.columns.filter(c=>c.field==='predicted_gdp' || economySelectedFields.has(c.field)).map(c=>c.field).join(','));
    const columns=[{field:'province_name',name:'Tỉnh',stage:'identity'},{field:'year',name:'Năm',stage:'identity'},{field:'month',name:'Tháng',stage:'identity'},...visible];
    const cell=(r,f)=>f==='province_name'?thoat(r[f]):['year','month'].includes(f)?String(r[f]??0):dinhDang(r[f],2)??'—';
    const groups=[['identity','Định danh'],['Raw','Dữ liệu đầu vào · Raw'],['Processed','Chỉ số tính toán · Processed']].map(([stage,label])=>{const count=columns.filter(c=>c.stage===stage).length;return count?`<th colspan="${count}" class="economy-group-${stage}">${label}</th>`:'';}).join('');
    const fitCard=b=>{const fit=data.hoi_quy[b];return `<article class="fit-card"><h3>${label(b)}</h3>`
      +`<p>β = ${dinhDang(fit.beta,4)??'—'} · R² = ${dinhDang(fit.r2,4)??'—'} · n = ${data.paired_count}</p>`
      +`<small>${fit.beta==null ? 'Chưa đủ quan sát dương hoặc phương sai để khớp hồi quy.' : 'ln(GRDP) = '+dinhDang(fit.alpha,4)+' + ('+dinhDang(fit.beta,4)+') × ln(SOL)'}</small></article>`;};
    $('economy-results').innerHTML=`<h2>Ánh sáng ban đêm và GRDP</h2><p>${thoat(scope)} · ${first}–${last}. GRDP: tỷ đồng; SOL: thang đo theo nguồn ảnh.</p>`
      +(!regression.some(r=>r.grdp_so_sanh!=null || r.grdp_hien_hanh!=null)?'<p class="canh">Chưa tìm thấy GRDP năm trong database đang mở; kiểm tra bộ dữ liệu đã nạp.</p>':'');
    $('economy-data-results').innerHTML=`<p class="nho">Bảng ${$('economy-frequency').value==='annual'?'theo năm':$('economy-frequency').value==='monthly'?'theo tháng':'năm và tháng'} · Định danh → Raw → Processed.</p>`
      +'<div class="economy-table-scroll"><table id="economy-data-table"><thead><tr>'
      +groups+'</tr><tr>'+columns.map(c=>`<th title="${thoat(c.definition || c.name)}">${thoat(c.name)}</th>`).join('')+'</tr></thead><tbody>'
      +data.dong.slice(0,100).map(r=>'<tr>'+columns.map(c=>`<td>${cell(r,c.field)}</td>`).join('')+'</tr>').join('')+'</tbody></table></div><div class="chan-bang economy-pages"><button id="economy-prev" type="button">← Trang trước</button><span id="economy-page"></span><button id="economy-next" type="button">Trang sau →</button></div>'
      +`<p class="nho">${data.dong.length} dòng (phân trang 100 dòng; CSV gồm toàn bộ). Ô thiếu giữ trống; GRDP chỉ có ở dòng năm.</p>`
      +(visible.length?`<a class="asset-link" href="/api/demo/economy.csv?${params}">Tải CSV theo bộ lọc</a>`:'<p class="nho">Chọn chỉ số trong bộ lọc để xuất CSV.</p>');
    $('economy-analysis-results').innerHTML='<h3>Quan hệ ánh sáng – GRDP</h3>'
      +`<p class="nho">Mẫu hồi quy gồm ${data.paired_count} cặp tỉnh–năm đủ hai loại GRDP và SOL dương, cùng nguồn VIIRS.</p>`
      +`<div class="fit-grid">${bases.map(fitCard).join('')}</div>`
      +'<div id="economy-scatter" class="economy-scatter"></div><p class="nho">Hồi quy dùng dữ liệu năm trong phạm vi đang chọn. Hồi quy log–log mô tả mối liên hệ, không chứng minh nhân quả.</p>'
      +(basis!=='so_sanh'?'<p class="nho">Giá hiện hành dùng đối chiếu, có ảnh hưởng biến động giá.</p>':'');
    let page=0;
    const drawPage=()=>{
      const pages=Math.max(1,Math.ceil(data.dong.length/100));page=Math.max(0,Math.min(page,pages-1));
      $('economy-data-table').querySelector('tbody').innerHTML=data.dong.slice(page*100,(page+1)*100).map(r=>'<tr>'+columns.map(c=>`<td>${cell(r,c.field)}</td>`).join('')+'</tr>').join('');
      $('economy-page').textContent=`Trang ${page+1}/${pages}`;$('economy-prev').disabled=page===0;$('economy-next').disabled=page===pages-1;
    };
    $('economy-prev').onclick=()=>{page--;drawPage();};$('economy-next').onclick=()=>{page++;drawPage();};drawPage();
    economyChartRenderer=()=>{
      if(typeof echarts==='undefined')return;
      economyChart=echarts.init($('economy-scatter'));
      const colors=['#ffc857','#6aa9ff'],series=[];
      bases.forEach((b,i)=>{
        const fit=data.hoi_quy[b];const points=data.regression_rows.filter(r=>r.paired && r.sol>0 && r['grdp_'+b]>0).map(r=>({value:[Math.log(r.sol),Math.log(r['grdp_'+b])],province:r.province_name,year:r.year}));
        series.push({name:label(b),type:'scatter',data:points,itemStyle:{color:colors[i]},symbolSize:7});
        if(fit.beta!=null && points.length){const xs=points.map(p=>p.value[0]),ends=[Math.min(...xs),Math.max(...xs)];series.push({name:'Hồi quy · '+label(b),type:'line',data:ends.map(x=>[x,fit.alpha+fit.beta*x]),symbol:'none',itemStyle:{color:colors[i]},lineStyle:{color:colors[i],width:2},silent:true});}
      });
      economyChart.setOption({textStyle:{color:'#9aa8be'},legend:{textStyle:{color:'#9aa8be'}},grid:{left:65,right:30,top:65,bottom:55},tooltip:{trigger:'item',formatter:p=>{const r=p.data;return r.province ? `${thoat(r.province)} · ${r.year}<br>ln(SOL): ${dinhDang(r.value[0],3)}<br>ln(GRDP): ${dinhDang(r.value[1],3)}`:'';}},xAxis:{type:'value',name:'ln(SOL)',nameLocation:'middle',nameGap:30,scale:true},yAxis:{type:'value',name:'ln(GRDP)',scale:true},series});
      if(!data.paired_count)$('economy-scatter').insertAdjacentHTML('afterend','<p class="canh">Không có mẫu hợp lệ để vẽ biểu đồ. Chọn khoảng năm hoặc phạm vi rộng hơn khi có dữ liệu.</p>');
      requestAnimationFrame(()=>economyChart?.resize());
    };
    selectEconomyView(economyView);
  }catch(error){if(request===economyRequest)$('economy-results').textContent=error.message;}
}
