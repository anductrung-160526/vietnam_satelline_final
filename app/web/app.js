'use strict';
/* VNGISDash — giao diện nguyên mẫu.
   Nguyên tắc: thiếu dữ liệu thì nói rõ là thiếu, không bao giờ vẽ số giả. */

const KHONG_CO = 'chưa có số liệu';
const $ = id => document.getElementById(id);

const trangThai = $('trang-thai');
const chonTinh  = $('chon-tinh');
const namTu     = $('nam-tu');
const namDen    = $('nam-den');
const theSoLieu = $('the-so-lieu');
const khungCanh = $('canh-bao');
const nutExport = $('nut-export');
const namNen    = $('nam-nen');
const namNenHien= $('nam-nen-hien');
const nenGhiChu = $('nen-ghi-chu');
const chiSoBanDo= $('chi-so-ban-do');

let danhMucChiSo = [];
let danhSachTinh = [];

async function layJSON(duongDan){
  const phanHoi = await fetch(duongDan);
  if(!phanHoi.ok) throw new Error(`${duongDan} → ${phanHoi.status}`);
  return phanHoi.json();
}

function so(v, chuSo = 2){
  if(v === null || v === undefined || Number.isNaN(v)) return null;
  return Number(Number(v).toFixed(chuSo));
}

function dinhDang(v, chuSo){
  if(v === null || v === undefined) return null;
  return Number(v).toLocaleString('vi-VN',
    {minimumFractionDigits:chuSo, maximumFractionDigits:chuSo});
}

/* ===================== tab ===================== */
document.querySelectorAll('.tab').forEach(nut => {
  nut.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('dang-chon', t === nut));
    document.querySelectorAll('.trang').forEach(t =>
      t.classList.toggle('an', t.id !== 'tab-' + nut.dataset.tab));
    if(nut.dataset.tab === 'du-lieu') veBang();
    if(nut.dataset.tab === 'ban-do' && banDo) banDo.resize();
    Object.values(bieuDo).forEach(b => b.resize());
  };
});

/* ===================== biểu đồ ===================== */
const THEME = {
  textStyle:{color:'#8b97b0',fontFamily:'system-ui,sans-serif',fontSize:11},
  grid:{left:52,right:16,top:16,bottom:28},
  tooltip:{trigger:'axis',backgroundColor:'#0d1322',borderColor:'#1f2940',
           textStyle:{color:'#e8ecf5',fontSize:12}},
  xAxis:{type:'category',axisLine:{lineStyle:{color:'#1f2940'}},axisTick:{show:false}},
  yAxis:{type:'value',splitLine:{lineStyle:{color:'#161d2e'}},axisLine:{show:false}},
};
const bieuDo = {};

function veBieuDo(id, nhan, loatSo, mau, haiTruc){
  const o = $(id);
  if(typeof echarts === 'undefined'){
    o.innerHTML = '<p class="ghi-chu">Không tải được thư viện biểu đồ (ECharts). '
      + 'Số liệu vẫn xem được ở bảng bên phải và trong tab Dữ liệu.</p>';
    return;
  }
  if(!bieuDo[id]) bieuDo[id] = echarts.init(o, null, {renderer:'canvas'});
  if(!loatSo.some(s => s.data.some(v => v !== null && v !== undefined))){
    bieuDo[id].clear();
    bieuDo[id].setOption({...THEME, xAxis:{show:false}, yAxis:{show:false},
      graphic:{type:'text', left:'center', top:'middle',
               style:{text:KHONG_CO, fill:'#8b97b0', font:'italic 13px system-ui'}}});
    return;
  }
  bieuDo[id].setOption({...THEME,
    xAxis:{...THEME.xAxis, data:nhan},
    yAxis: haiTruc ? [{...THEME.yAxis}, {...THEME.yAxis, splitLine:{show:false}}] : THEME.yAxis,
    grid: haiTruc ? {...THEME.grid, top:28, right:52}
                  : (loatSo.length > 1 ? {...THEME.grid, top:28} : THEME.grid),
    legend: loatSo.length > 1 ? {top:0, right:haiTruc ? 52 : 0,
                                 textStyle:{color:'#8b97b0',fontSize:10}} : undefined,
    series: loatSo.map((s,i) => ({
      name:s.name, type:'line', data:s.data, smooth:true, showSymbol:false,
      yAxisIndex: haiTruc ? i : 0,
      connectNulls:false, lineStyle:{width:2},
      itemStyle:{color: s.color || mau[i % mau.length]},
    }))}, true);
}

/* ===================== bảng bên phải của một tỉnh ===================== */
function oSo(ten, giaTri, donVi){
  const co = giaTri !== null && giaTri !== undefined;
  return `<div class="o-so"><div class="ten">${ten}</div>
    <div class="gia-tri${co ? '' : ' trong'}">${
      co ? giaTri.toLocaleString('vi-VN') + (donVi ? ' ' + donVi : '') : KHONG_CO
    }</div></div>`;
}

function cuoi(mang, khoa){
  for(let i = mang.length - 1; i >= 0; i--){
    if(mang[i][khoa] !== null && mang[i][khoa] !== undefined) return mang[i];
  }
  return null;
}

async function veTinh(tieuDiem = true){
  const ma = chonTinh.value;
  if(!ma) return;
  nutExport.disabled = true;
  const tu = Number(namTu.value), den = Number(namDen.value);
  if(tu > den){
    khungCanh.innerHTML = '<div class="canh thieu">Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.</div>';
    return;
  }
  let d;
  try{
    d = await layJSON(`/api/indices?ma_tinh=${ma}&nam_tu=${tu}&nam_den=${den}`);
  }catch(loi){
    khungCanh.innerHTML = `<div class="canh thieu">Không lấy được dữ liệu: ${loi.message}</div>`;
    return;
  }

  const namDemArr  = d.dem.map(r => r.nam);
  const namNgayArr = d.ngay.map(r => r.nam);
  veBieuDo('bd-dem', namDemArr,
    [{name:'Tổng độ sáng (SOL)', data:d.dem.map(r => so(r.sol_ntl))}], ['#ffc857']);
  veBieuDo('bd-dien-tich', namDemArr,
    [{name:'Số điểm ảnh sáng', data:d.dem.map(r => so(r.lit_pixels, 0))},
     {name:'Mật độ sáng',      data:d.dem.map(r => so(r.mat_do_ntl, 3))}],
    ['#5ec8d8','#7ddc8a'], true);
  veBieuDo('bd-ngay', namNgayArr,
    [{name:'NDVI', data:d.ngay.map(r => so(r.NDVI_mean, 3))},
     {name:'NDBI', data:d.ngay.map(r => so(r.NDBI_mean, 3))},
     {name:'MNDWI',data:d.ngay.map(r => so(r.MNDWI_mean, 3))}], ['#7ddc8a','#ff9f68','#5ec8d8']);

  const demCuoi = cuoi(d.dem, 'sol_ntl');
  const ngayCuoi = cuoi(d.ngay, 'NDVI_mean');
  const kinhTeCuoi = cuoi(d.kinh_te, 'gdp') || cuoi(d.kinh_te, 'dan_so');
  theSoLieu.innerHTML =
    oSo(`Tổng độ sáng${demCuoi ? ' (' + demCuoi.nam + ')' : ''}`, so(demCuoi?.sol_ntl)) +
    oSo('Mật độ sáng',  so(demCuoi?.mat_do_ntl, 3)) +
    oSo('Diện tích tỉnh', so(demCuoi?.dien_tich_km2 ?? ngayCuoi?.dien_tich_km2, 0), 'km²') +
    oSo(`NDVI${ngayCuoi ? ' (' + ngayCuoi.nam + ')' : ''}`, so(ngayCuoi?.NDVI_mean, 3)) +
    oSo('Dân số', so(kinhTeCuoi?.dan_so, 0)) +
    oSo('GDP',    so(kinhTeCuoi?.gdp, 0));

  const canh = [];
  if(d.gia_lap) canh.push(['gia-lap','⚠ SỐ LIỆU GIẢ LẬP — chỉ minh họa giao diện. '
    + 'Không dùng cho báo cáo. Chỉ số thật đang được tính.']);
  if(d.thieu_du_lieu.dem)
    canh.push(['thieu','Chưa có chỉ số ảnh đêm cho tỉnh này. Chạy bước tính chỉ số của task_pipeline/derive.py.']);
  if(d.thieu_du_lieu.ngay) canh.push(['thieu','Chưa có chỉ số ảnh ngày cho tỉnh này.']);
  if(d.thieu_du_lieu.kinh_te)
    canh.push(['thieu','Chưa có dữ liệu dân số và GDP — chờ giảng viên cung cấp.']);
  (d.canh_bao || []).filter(v => !v.startsWith('SỐ LIỆU GIẢ LẬP'))
    .forEach(v => canh.push(['', v]));
  khungCanh.innerHTML = canh.map(([l,v]) => `<div class="canh ${l}">${v}</div>`).join('');

  nutExport.disabled = false;
  nutExport.onclick = () => {
    window.location = `/api/export.zip?ma_tinh=${ma}&nam_tu=${tu}&nam_den=${den}`;
  };
  if(tieuDiem) tieuDiemTinh(ma);
}

/* ===================== bản đồ ===================== */
let banDo, ranhGioi = null, namCoAnh = [], thongTinNen = null, maDangXem = null;

const THANG = ['#10233a','#1d4a6b','#2d7f8f','#6fbf87','#d9d16a','#f0944a','#e2563d'];

function kieuNen(){
  /* Không gọi dịch vụ bản đồ ngoài: nền tối + ranh giới và ảnh đêm của chính dự án. */
  return {version:8, sources:{}, layers:[{id:'nen', type:'background',
          paint:{'background-color':'#05070d'}}]};
}

function bienDo(dacTrung){
  /* Hộp bao của một Feature (Polygon hoặc MultiPolygon). */
  const g = dacTrung.geometry;
  const vong = g.type === 'Polygon' ? g.coordinates : g.coordinates.flat();
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  vong.forEach(r => r.forEach(([x,y]) => {
    if(x < x0) x0 = x; if(x > x1) x1 = x;
    if(y < y0) y0 = y; if(y > y1) y1 = y;
  }));
  return [[x0,y0],[x1,y1]];
}

function matNa(dacTrung){
  /* Hình chữ nhật phủ cả thế giới, khoét lỗ đúng hình tỉnh -> phần ngoài bị tối đi.
     Vành ngoài đi ngược chiều kim đồng hồ, các lỗ giữ nguyên chiều của dữ liệu gốc. */
  const g = dacTrung.geometry;
  const lo = g.type === 'Polygon' ? g.coordinates : g.coordinates.flat();
  return {type:'Feature', properties:{}, geometry:{type:'Polygon',
    coordinates:[[[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]], ...lo]}};
}

async function dungBanDo(){
  if(typeof maplibregl === 'undefined'){
    nenGhiChu.textContent = 'Không tải được thư viện bản đồ (MapLibre GL). '
      + 'Phần chỉ số và tab Dữ liệu vẫn hoạt động bình thường.';
    namNen.disabled = true;
    return;
  }
  banDo = new maplibregl.Map({container:'ban-do', style:kieuNen(),
    center:[106.0, 16.3], zoom:4.6, attributionControl:false});
  banDo.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');

  await new Promise(ok => banDo.on('load', ok));

  try{
    ranhGioi = await layJSON('/api/boundaries.geojson');
  }catch{
    nenGhiChu.textContent = 'Chưa có ranh giới tỉnh (cần GADM 4.1 — chạy build_boundaries.py). '
      + 'Chọn tỉnh bằng danh sách bên phải.';
  }

  if(ranhGioi){
    banDo.addSource('tinh', {type:'geojson', data:ranhGioi, promoteId:'ma_tinh'});
    banDo.addSource('mat-na', {type:'geojson',
      data:{type:'FeatureCollection', features:[]}});
    banDo.addLayer({id:'tinh-to', type:'fill', source:'tinh',
      paint:{'fill-color':['coalesce',['feature-state','mau'],'#16203a'],
             'fill-opacity':['case',['boolean',['feature-state','ro'],false],0.95,0.78]}});
    banDo.addLayer({id:'tinh-vien', type:'line', source:'tinh',
      paint:{'line-color':'#46597d','line-width':0.7}});
    /* Mặt nạ nằm TRÊN các tỉnh để che hết phần ngoài tỉnh đang xem. */
    banDo.addLayer({id:'mat-na-lop', type:'fill', source:'mat-na',
      paint:{'fill-color':'#05070d','fill-opacity':0.88}});
    banDo.addLayer({id:'tinh-vien-dam', type:'line', source:'tinh',
      filter:['==','ma_tinh',''],
      paint:{'line-color':'#ffc857','line-width':2.2}});

    banDo.on('click','tinh-to', e => {
      const ma = e.features[0].properties.ma_tinh;
      if(ma){ chonTinh.value = String(ma).padStart(2,'0'); veTinh(); }
    });
    banDo.on('mouseenter','tinh-to',()=>banDo.getCanvas().style.cursor='pointer');
    banDo.on('mouseleave','tinh-to',()=>banDo.getCanvas().style.cursor='');
  }

  await napAnhNen();
  await toMau();
  if(!ranhGioi && !namCoAnh.length) $('khung-ban-do').classList.add('trong');
}

function toanQuoc(){
  maDangXem = null;
  $('hop-pham-vi').classList.remove('hien');
  if(!banDo) return;
  if(banDo.getSource('mat-na'))
    banDo.getSource('mat-na').setData({type:'FeatureCollection', features:[]});
  if(banDo.getLayer('tinh-vien-dam')) banDo.setFilter('tinh-vien-dam',['==','ma_tinh','']);
  if(ranhGioi) banDo.fitBounds(bienDoTatCa(), {padding:36, duration:600});
  else banDo.easeTo({center:[106.0,16.3], zoom:4.6, duration:600});
}

function bienDoTatCa(){
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  ranhGioi.features.forEach(f => {
    const [[a,b],[c,d]] = bienDo(f);
    if(a < x0) x0 = a; if(c > x1) x1 = c;
    if(b < y0) y0 = b; if(d > y1) y1 = d;
  });
  return [[x0,y0],[x1,y1]];
}

function tieuDiemTinh(ma){
  maDangXem = ma;
  const ten = (danhSachTinh.find(t => t.ma_tinh === ma) || {}).ten_tinh || ma;
  $('ten-tinh-dang-xem').textContent = ten;
  $('hop-pham-vi').classList.add('hien');
  if(!banDo || !ranhGioi) return;
  const f = ranhGioi.features.find(x => String(x.properties.ma_tinh).padStart(2,'0') === ma);
  if(!f){
    nenGhiChu.textContent = `Không tìm thấy ranh giới của ${ten} trong file GeoJSON.`;
    return;
  }
  banDo.getSource('mat-na').setData({type:'FeatureCollection', features:[matNa(f)]});
  banDo.setFilter('tinh-vien-dam',['==','ma_tinh', f.properties.ma_tinh]);
  banDo.fitBounds(bienDo(f), {padding:60, duration:700, maxZoom:10});
}

$('nut-toan-quoc').onclick = toanQuoc;

async function toMau(){
  if(!banDo || !ranhGioi) return;
  const ma = chiSoBanDo.value, nam = Number(namNen.value);
  let d;
  try{ d = await layJSON(`/api/choropleth?chi_so=${ma}&nam=${nam}`); }
  catch{ return; }
  const nho = d.nho_nhat, lon = d.lon_nhat;
  ranhGioi.features.forEach(f => {
    const code = String(f.properties.ma_tinh).padStart(2,'0');
    const v = d.gia_tri[code];
    let mau = '#16203a';            // không có số liệu: xám xanh, phân biệt rõ với bậc thấp nhất
    if(v !== undefined && v !== null && lon !== null && lon > nho){
      /* thang căn theo căn bậc hai: độ sáng lệch rất mạnh, tuyến tính thì 60 tỉnh cùng một màu */
      const t = Math.sqrt((v - nho) / (lon - nho));
      mau = THANG[Math.min(THANG.length - 1, Math.floor(t * THANG.length))];
    }
    banDo.setFeatureState({source:'tinh', id:f.properties.ma_tinh},
                          {mau, ro:v !== undefined && v !== null});
  });
  const e = d.chi_so;
  $('thang-mau').innerHTML = nho === null
    ? `<span>${KHONG_CO} cho năm ${nam}</span>`
    : `<b>${dinhDang(nho, e.chu_so)}</b>
       <span class="dai" style="background:linear-gradient(90deg,${THANG.join(',')})"></span>
       <b>${dinhDang(lon, e.chu_so)}</b><span>${e.don_vi}</span>`;
}

async function napAnhNen(){
  let b;
  try{ b = await layJSON('/api/basemap'); }
  catch{ return; }
  thongTinNen = b;
  namCoAnh = b.nam || [];
  if(!namCoAnh.length || !b.tiles){
    nenGhiChu.textContent = namCoAnh.length
      ? 'Có ảnh nền nhưng chưa cài TiTiler nên chưa phục vụ được ô bản đồ.'
      : 'Chưa có ảnh nền ban đêm dạng COG. Chạy: python3 -m app.data.build_cogs';
  }
}

function doiAnhNen(nam){
  if(!banDo || !thongTinNen || !thongTinNen.tiles) return;
  const muc = (thongTinNen.chi_tiet || []).find(c => c.nam === nam);
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  if(!muc) return;
  banDo.addSource('anh-dem', {type:'raster', tileSize:256,
    tiles:[`${thongTinNen.tiles}${encodeURIComponent(muc.duong_dan)}&rescale=0,60&colormap_name=inferno`]});
  banDo.addLayer({id:'anh-dem', type:'raster', source:'anh-dem',
    paint:{'raster-opacity':0.9}}, banDo.getLayer('tinh-to') ? 'tinh-to' : undefined);
}

namNen.oninput = () => {
  namNenHien.textContent = namNen.value;
  toMau();
  doiAnhNen(Number(namNen.value));
};
chiSoBanDo.onchange = toMau;

/* ===================== tab dữ liệu (kiểu WDI) ===================== */
let bangHienTai = null;

function thamSoBang(){
  const tu = Number($('dl-nam-tu').value), den = Number($('dl-nam-den').value);
  return {chiSo:$('dl-chi-so').value, tu, den};
}

async function veBang(){
  const {chiSo, tu, den} = thamSoBang();
  const than = document.querySelector('#dl-bang tbody');
  const dau  = document.querySelector('#dl-bang thead');
  if(tu > den){
    $('dl-canh-bao').innerHTML = '<div class="canh thieu">Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.</div>';
    return;
  }
  let d;
  try{ d = await layJSON(`/api/panel?chi_so=${chiSo}&nam_tu=${tu}&nam_den=${den}`); }
  catch(loi){
    $('dl-canh-bao').innerHTML = `<div class="canh thieu">Không lấy được bảng: ${loi.message}</div>`;
    return;
  }
  bangHienTai = d;
  const e = d.chi_so;
  $('dl-mo-ta').textContent = `${e.mo_ta} Đơn vị: ${e.don_vi}.`;
  $('dl-tom-tat').textContent =
    `${d.so_tinh_co_du_lieu}/${d.dong.length} tỉnh có số liệu · ${d.nam.length} năm `
    + `(${tu}–${den}) · nguồn bảng ${e.bang}`;
  $('dl-canh-bao').innerHTML = (d.canh_bao || [])
    .map(v => `<div class="canh">${v}</div>`).join('');

  dau.innerHTML = '<tr><th>Mã</th><th>Tỉnh / thành phố</th>'
    + d.nam.map(n => `<th>${n}</th>`).join('') + '</tr>';
  loc();
}

function loc(){
  if(!bangHienTai) return;
  const tim = ($('dl-loc-tinh').value || '').trim().toLowerCase();
  const e = bangHienTai.chi_so;
  const than = document.querySelector('#dl-bang tbody');
  const dong = bangHienTai.dong.filter(r =>
    !tim || r.ten_tinh.toLowerCase().includes(tim) || r.ma_tinh.includes(tim));
  than.innerHTML = dong.map(r => '<tr><td class="ma">' + r.ma_tinh + '</td><td>' + r.ten_tinh + '</td>'
    + r.gia_tri.map(v => v === null
        ? '<td class="trong">··</td>'
        : `<td>${dinhDang(v, e.chu_so)}</td>`).join('')
    + '</tr>').join('')
    || `<tr><td colspan="${bangHienTai.nam.length + 2}" class="trong">Không có tỉnh nào khớp.</td></tr>`;
}

$('dl-loc-tinh').oninput = loc;
$('dl-chi-so').onchange = veBang;
$('dl-nam-tu').onchange = veBang;
$('dl-nam-den').onchange = veBang;
$('dl-tai-rong').onclick = () => taiBang('rong');
$('dl-tai-dai').onclick  = () => taiBang('dai');

function taiBang(dang){
  const {chiSo, tu, den} = thamSoBang();
  window.location = `/api/panel.csv?chi_so=${chiSo}&nam_tu=${tu}&nam_den=${den}&dang=${dang}`;
}

/* ===================== khởi động ===================== */
(async function khoiDong(){
  try{
    const suc = await layJSON('/api/health');
    trangThai.textContent = suc.ok ? `${suc.so_tinh} tỉnh` : 'chưa có dữ liệu';
    trangThai.className = 'pill ' + (suc.ok ? 'ok' : 'loi');
  }catch{
    trangThai.textContent = 'API không phản hồi';
    trangThai.className = 'pill loi';
    return;
  }

  danhMucChiSo = (await layJSON('/api/indicators')).chi_so;
  const tuyChon = danhMucChiSo.map(c => {
    const co = c.so_tinh ? '' : ' — chưa có số liệu';
    return `<option value="${c.ma}">${c.ten}${co}</option>`;
  }).join('');
  chiSoBanDo.innerHTML = tuyChon;
  $('dl-chi-so').innerHTML = tuyChon;

  danhSachTinh = (await layJSON('/api/provinces')).tinh;
  chonTinh.innerHTML = danhSachTinh.map(t => {
    const co = t.so_nam_dem || t.so_nam_ngay;
    return `<option value="${t.ma_tinh}">${t.ten_tinh}${co ? '' : ' — chưa có số liệu'}</option>`;
  }).join('');
  const dauTien = danhSachTinh.find(t => t.so_nam_dem || t.so_nam_ngay) || danhSachTinh[0];
  chonTinh.value = dauTien.ma_tinh;
  chonTinh.onchange = () => veTinh(true);
  namTu.onchange = () => veTinh(maDangXem !== null);
  namDen.onchange = () => veTinh(maDangXem !== null);

  try{
    await dungBanDo();
  }catch(loi){
    nenGhiChu.textContent = 'Bản đồ không khởi tạo được: ' + loi.message
      + '. Phần chỉ số vẫn hoạt động.';
  }
  await veTinh(false);      // số liệu của tỉnh đầu tiên, nhưng bản đồ vẫn ở toàn quốc
  toanQuoc();
  window.addEventListener('resize', () => Object.values(bieuDo).forEach(b => b.resize()));
})();
