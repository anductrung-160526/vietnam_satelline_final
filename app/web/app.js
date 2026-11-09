"use strict";
/* VNGISDash — tab "Ảnh đêm" là trình xem ảnh, tab "Dữ liệu" là bảng tra cứu.
   Nguyên tắc: thiếu dữ liệu thì nói rõ là thiếu, không bao giờ vẽ số giả. */

const $ = id => document.getElementById(id);

let danhSachTinh = [];
let ranhGioi = null;
let thongTinNen = null;      // /api/basemap
let maDangXem = null;        // null = toàn quốc
let banDo = null;

async function layJSON(duongDan){
  const r = await fetch(duongDan);
  if(!r.ok) throw new Error(`${duongDan} → ${r.status}`);
  return r.json();
}
const dinhDang = (v, c = 2) => (v === null || v === undefined)
  ? null : Number(v).toLocaleString('vi-VN', {minimumFractionDigits:c, maximumFractionDigits:c});

/* ===================== thanh kéo đổi độ rộng cột lọc ===================== */
(function keoCot(){
  const thanh = $('thanh-keo');
  let dangKeo = false;
  const dat = x => {
    const rong = Math.min(Math.max(x, 180), Math.min(560, window.innerWidth - 240));
    document.documentElement.style.setProperty('--rong-cot', rong + 'px');
    if(banDo) banDo.resize();
  };
  thanh.addEventListener('pointerdown', e => {
    dangKeo = true; thanh.classList.add('dang-keo');
    thanh.setPointerCapture(e.pointerId); e.preventDefault();
  });
  thanh.addEventListener('pointermove', e => { if(dangKeo) dat(e.clientX); });
  const thoi = () => { dangKeo = false; thanh.classList.remove('dang-keo'); };
  thanh.addEventListener('pointerup', thoi);
  thanh.addEventListener('pointercancel', thoi);
  thanh.addEventListener('dblclick', () => dat(280));
})();

/* ===================== bản đồ ===================== */
/* Hai mức sáng cho đường ranh giới. Khi xem toàn quốc thì đường viền chỉ là nền, phải mờ
   để không át ảnh đêm. Khi đã chọn một tỉnh thì người dùng cần thấy rõ ranh giới các tỉnh
   xung quanh để định vị, nên sáng hẳn lên. */
const VIEN = {
  mo:    {mau:'#3b4b6b', rong:0.6, dam:0.85},
  sang:  {mau:'#9db4dd', rong:1.1, dam:1.0},
};

function kieuNen(){
  return {version:8, sources:{}, layers:[{id:'nen', type:'background',
          paint:{'background-color':'#05070d'}}]};
}

function vongCua(f){
  const g = f.geometry;
  return g.type === 'Polygon' ? g.coordinates : g.coordinates.flat();
}

function bienDo(f){
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  vongCua(f).forEach(r => r.forEach(([x,y]) => {
    if(x < x0) x0 = x; if(x > x1) x1 = x;
    if(y < y0) y0 = y; if(y > y1) y1 = y;
  }));
  return [[x0,y0],[x1,y1]];
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

/* Đa giác phủ cả thế giới, khoét lỗ đúng hình cần giữ -> phần ngoài bị che tối.
   Đây là cách "cắt ảnh theo ranh giới" ngay trên màn hình, không phải cắt lại file. */
function matNa(dacTrungs){
  const lo = [];
  dacTrungs.forEach(f => vongCua(f).forEach(r => lo.push(r)));
  return {type:'Feature', properties:{}, geometry:{type:'Polygon',
    coordinates:[[[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]], ...lo]}};
}

function datMatNa(){
  if(!banDo || !ranhGioi || !banDo.getSource('mat-na')) return;
  const rong = {type:'FeatureCollection', features:[]};
  /* Toàn quốc thì không che: ảnh vốn đã chỉ phủ lãnh thổ Việt Nam, mà mặt nạ gộp vòng của
     cả 63 tỉnh là hình nặng nhất, dễ dựng hỏng nhất. Chỉ che khi đã chọn một tỉnh. */
  if(!maDangXem){ banDo.getSource('mat-na').setData(rong); return; }
  const giu = ranhGioi.features.filter(
    f => String(f.properties.ma_tinh).padStart(2,'0') === maDangXem);
  if(!giu.length){
    /* Không tìm thấy ranh giới của tỉnh này: che hết sẽ ra màn hình đen trơn, tệ hơn là
       không che. Nói ra thay vì để người dùng nhìn một khung trống. */
    banDo.getSource('mat-na').setData(rong);
    nhacMatNa(`Không tìm thấy ranh giới của mã tỉnh ${maDangXem} trong file GeoJSON, `
      + 'nên không cắt được theo ranh giới. Kiểm tra: /api/boundaries-info');
    return;
  }
  nhacMatNa(null);
  banDo.getSource('mat-na').setData({type:'FeatureCollection', features:[matNa(giu)]});
}

function nhacMatNa(chu){
  const cu = document.getElementById('nhac-mat-na');
  if(cu) cu.remove();
  if(!chu) return;
  $('canh-bao').insertAdjacentHTML('beforeend',
    `<div class="canh thieu" id="nhac-mat-na">${chu}</div>`);
}

async function dungBanDo(){
  if(typeof maplibregl === 'undefined'){
    $('canh-bao').innerHTML = '<div class="canh thieu">Không tải được thư viện bản đồ '
      + '(MapLibre GL). Tab Dữ liệu vẫn hoạt động.</div>';
    return;
  }
  banDo = new maplibregl.Map({container:'ban-do', style:kieuNen(),
    center:[106.0, 16.3], zoom:4.8, attributionControl:false});
  banDo.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');
  banDo.addControl(new maplibregl.ScaleControl({maxWidth:120, unit:'metric'}), 'bottom-right');
  await new Promise(ok => banDo.on('load', ok));

  try{ ranhGioi = await layJSON('/api/boundaries.geojson'); }
  catch{
    themCanhBao('thieu', 'Chưa có ranh giới tỉnh. Chạy: python -m app.data.build_boundaries --tai-gadm');
  }

  if(ranhGioi){
    banDo.addSource('tinh', {type:'geojson', data:ranhGioi, promoteId:'ma_tinh'});
    banDo.addSource('mat-na', {type:'geojson', data:{type:'FeatureCollection', features:[]}});
    /* Lớp bắt sự kiện bấm: trong suốt, nằm dưới ảnh và mặt nạ. */
    banDo.addLayer({id:'tinh-bat', type:'fill', source:'tinh',
      paint:{'fill-color':'#16203a','fill-opacity':0.001}});
    /* Che hẳn, không để lọt 10% ánh sáng của vùng ngoài ranh giới. */
    banDo.addLayer({id:'mat-na-lop', type:'fill', source:'mat-na',
      paint:{'fill-color':'#05070d','fill-opacity':1}});
    banDo.addLayer({id:'tinh-vien', type:'line', source:'tinh',
      paint:{'line-color':VIEN.mo.mau, 'line-width':VIEN.mo.rong,
             'line-opacity':VIEN.mo.dam}});
    /* Quầng sáng mảnh dưới đường viền tỉnh đang chọn, để nó nổi trên nền ảnh đêm. */
    banDo.addLayer({id:'tinh-vien-quang', type:'line', source:'tinh',
      filter:['==','ma_tinh',''],
      paint:{'line-color':'#ffc857','line-width':7,'line-opacity':0.22,'line-blur':4}});
    banDo.addLayer({id:'tinh-vien-dam', type:'line', source:'tinh',
      filter:['==','ma_tinh',''],
      paint:{'line-color':'#ffd87a','line-width':2.4}});
    banDo.on('click','tinh-bat', e => {
      const ma = String(e.features[0].properties.ma_tinh).padStart(2,'0');
      $('chon-tinh').value = ma; chonPhamVi(ma);
    });
    banDo.on('mouseenter','tinh-bat',()=>banDo.getCanvas().style.cursor='pointer');
    banDo.on('mouseleave','tinh-bat',()=>banDo.getCanvas().style.cursor='');
    banDo.fitBounds(bienDoTatCa(), {padding:30, duration:0});
    datMatNa();
  }
}

function themCanhBao(loai, chu){
  $('canh-bao').insertAdjacentHTML('beforeend', `<div class="canh ${loai}">${chu}</div>`);
}

/* ===================== ảnh đêm ===================== */
function doiAnhNen(nam){
  if(!banDo) return;
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  const muc = (thongTinNen?.chi_tiet || []).find(c => c.nam === nam);
  if(!muc || !thongTinNen.tiles){ veThongTin(null); return; }
  const nguon = {type:'raster', tileSize:256,
    tiles:[`${thongTinNen.tiles}${encodeURIComponent(muc.duong_dan)}`
           + `&rescale=0,60&colormap_name=inferno&nodata=-9999`]};
  /* Giới hạn theo phạm vi ảnh: thiếu nó thì bản đồ xin ô khắp thế giới và TiTiler
     trả 500 cho mọi ô nằm ngoài ảnh — hàng trăm lượt gọi hỏng mỗi lần mở trang. */
  if([muc.tay, muc.nam_do, muc.dong, muc.bac].every(v => typeof v === 'number')){
    nguon.bounds = [muc.tay, muc.nam_do, muc.dong, muc.bac];
  }
  banDo.addSource('anh-dem', nguon);
  /* Ảnh nằm DƯỚI mặt nạ, nên phần ngoài ranh giới bị che — ảnh hiện đúng trong ranh giới. */
  banDo.addLayer({id:'anh-dem', type:'raster', source:'anh-dem',
    paint:{'raster-opacity':1}}, 'mat-na-lop');
  veThongTin(muc);
}

function veThongTin(muc){
  const o = $('thong-tin-anh');
  if(!muc){
    o.innerHTML = '';
    $('nut-tai-anh').disabled = true;
    $('ghi-chu-tai').textContent = '';
    $('thang-mau').style.display = 'none';
    return;
  }
  const mb = muc.dung_luong_byte ? (muc.dung_luong_byte / 1048576).toFixed(1) + ' MB' : '—';
  const donVi = muc.nguon_anh === 'DMSP' ? 'DN 0–63' : 'nW/cm²/sr';
  o.innerHTML =
    `<div><span>Nguồn</span><span>${muc.nguon_anh || '—'}</span></div>` +
    `<div><span>Năm</span><span>${muc.nam}</span></div>` +
    `<div><span>Độ phân giải</span><span>${muc.nguon_anh === 'DMSP' ? '1 km' : '500 m'}</span></div>` +
    `<div><span>Đơn vị</span><span>${donVi}</span></div>` +
    `<div><span>Dung lượng</span><span>${mb}</span></div>`;
  $('nut-tai-anh').disabled = false;
  $('ghi-chu-tai').textContent = 'GeoTIFF toàn quốc của năm đang chọn, mở được bằng QGIS.';
  $('thang-mau').style.display = '';
  $('thang-mau').innerHTML =
    `<b>0</b><span class="dai" style="background:linear-gradient(90deg,`
    + `#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4)"></span><b>60</b><span>${donVi}</span>`;
}

function chonPhamVi(ma){
  maDangXem = ma || null;
  const ten = ma ? (danhSachTinh.find(t => t.ma_tinh === ma) || {}).ten_tinh : 'Toàn quốc';
  $('nhan-pham-vi').textContent = ten || 'Toàn quốc';
  if(!banDo || !ranhGioi) return;
  datMatNa();
  const kieu = ma ? VIEN.sang : VIEN.mo;
  banDo.setPaintProperty('tinh-vien', 'line-color', kieu.mau);
  banDo.setPaintProperty('tinh-vien', 'line-width', kieu.rong);
  banDo.setPaintProperty('tinh-vien', 'line-opacity', kieu.dam);
  banDo.setFilter('tinh-vien-dam', ['==','ma_tinh', ma || '']);
  banDo.setFilter('tinh-vien-quang', ['==','ma_tinh', ma || '']);
  const f = ma && ranhGioi.features.find(x => String(x.properties.ma_tinh).padStart(2,'0') === ma);
  banDo.fitBounds(f ? bienDo(f) : bienDoTatCa(),
                  {padding: f ? 60 : 30, duration:600, maxZoom:10});
}

$('nut-toan-quoc').onclick = () => { $('chon-tinh').value = ''; chonPhamVi(null); };
$('nut-tai-anh').onclick = () => {
  window.location = `/api/anh-dem.tif?nam=${$('chon-nam').value}`;
};

/* ===================== khởi động ===================== */
(async function khoiDong(){
  try{
    const suc = await layJSON('/api/health');
    $('trang-thai').textContent = suc.ok ? `${suc.so_tinh} tỉnh` : 'chưa có dữ liệu';
    $('trang-thai').className = 'pill ' + (suc.ok ? 'ok' : 'loi');
  }catch{
    $('trang-thai').textContent = 'API không phản hồi';
    $('trang-thai').className = 'pill loi';
    return;
  }

  danhSachTinh = (await layJSON('/api/provinces')).tinh;
  $('chon-tinh').innerHTML = '<option value="">Toàn quốc</option>'
    + danhSachTinh.map(t => `<option value="${t.ma_tinh}">${t.ten_tinh}</option>`).join('');
  $('chon-tinh').onchange = () => chonPhamVi($('chon-tinh').value || null);

  try{ thongTinNen = await layJSON('/api/basemap'); }catch{ thongTinNen = null; }
  const nam = thongTinNen?.nam || [];
  const chon = $('chon-nam'), truot = $('nam-truot');
  if(nam.length){
    chon.innerHTML = nam.slice().reverse().map(n => `<option value="${n}">${n}</option>`).join('');
    truot.min = Math.min(...nam); truot.max = Math.max(...nam); truot.value = truot.max;
    chon.value = truot.max;
    chon.onchange = () => { truot.value = chon.value; doiAnhNen(Number(chon.value)); };
    truot.oninput  = () => { chon.value = truot.value; doiAnhNen(Number(truot.value)); };
  }else{
    chon.innerHTML = '<option>— chưa có ảnh —</option>';
    chon.disabled = truot.disabled = true;
    themCanhBao('thieu', 'Chưa có ảnh đêm dạng COG. Trên máy có dữ liệu, chạy:<br>'
      + '<code>python -m app.data.build_cogs --root E:\\SatelliteData --kinds VIIRS DMSP</code>');
  }
  if(!thongTinNen?.tiles && nam.length){
    themCanhBao('thieu', 'Có ảnh nhưng chưa cài TiTiler nên chưa phục vụ được ô bản đồ: '
      + '<code>pip install -r app/requirements.txt</code>');
  }

  await dungBanDo();
  chonPhamVi(null);
  if(nam.length) doiAnhNen(Number(chon.value)); else veThongTin(null);
})();
