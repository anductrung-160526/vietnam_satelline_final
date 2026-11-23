"use strict";
/* VNGISDash — ba màn: Ảnh đêm, Chỉ số đêm, Chỉ số kinh tế đêm.
   Nguyên tắc: thiếu dữ liệu thì nói rõ là thiếu, không bao giờ vẽ số giả. */

const $ = id => document.getElementById(id);

let danhSachTinh = [];
let ranhGioi = null;

// File provinces.geojson dựng trước đợt đổi tên cột còn mang khoá tiếng Việt
// (ma_tinh / ten_tinh). Đổi tên tại chỗ khi nạp để bản cũ trên máy vẫn dùng được,
// khỏi phải tải lại GADM 50 MB. Bản dựng mới đã ghi thẳng province_code.
function chuanHoaRanhGioi(fc){
  (fc.features || []).forEach(f => {
    const p = f.properties || (f.properties = {});
    if(p.province_code == null && p.ma_tinh != null) p.province_code = p.ma_tinh;
    if(p.province_name == null && p.ten_tinh != null) p.province_name = p.ten_tinh;
    if(p.province_code != null) p.province_code = String(p.province_code).padStart(2,'0');
  });
}
let thongTinNen = null;      // /api/basemap của bước đang chọn
let maDangXem = null;        // null = toàn quốc
let banDo = null;
let buoc = 'nam';            // 'nam' hoặc 'thang'
let cacMoc = [];             // các mốc có ảnh, theo thứ tự thời gian
let danhMuc = [];            // /api/indicators
const THANG_VN = ['01','02','03','04','05','06','07','08','09','10','11','12'];
const tenMoc = m => m.month ? `${THANG_VN[m.month - 1]}/${m.year}` : String(m.year);
const maMoc  = m => m.month ? `${m.year}-${String(m.month).padStart(2,'0')}` : String(m.year);

async function layJSON(duongDan){
  // Không dùng JSON cũ trong cache sau khi cập nhật database/code.
  const r = await fetch(duongDan, {cache:'no-store'});
  if(typeof checkDemoSnapshot === 'function' && r.headers.has('X-Snapshot-ID'))
    checkDemoSnapshot({snapshot_id:r.headers.get('X-Snapshot-ID') || null});
  if(!r.ok){
    let detail='';try{detail=(await r.json()).detail || '';}catch{}
    throw new Error(detail || `${duongDan} → ${r.status}`);
  }
  return r.json();
}
const dinhDang = (v, c = 2) => (v === null || v === undefined)
  ? null : Number(v).toLocaleString('vi-VN', {minimumFractionDigits:c, maximumFractionDigits:c});
const thoat = t => String(t).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* Bỏ dấu để gõ "ba ria" cũng ra "Bà Rịa - Vũng Tàu": người dùng hiếm khi gõ đủ dấu. */
const khongDau = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase().trim();

/* ===================== chuyển màn ===================== */
const MAN = {anh:'man-anh', chiso:'man-chiso', kinhte:'man-kinhte',spatial:'man-spatial'};
function chuyenMan(ten){
  document.querySelectorAll('.thanh-man button').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.man === ten)));
  for(const [k, id] of Object.entries(MAN)) $(id).hidden = k !== ten;
  for(const id of ['context-year','context-month'])$(id).closest('label').hidden=ten==='spatial';
  if(ten!=='spatial')syncContext();
  if(ten === 'anh' && banDo) banDo.resize();
  if(ten === 'kinhte') requestAnimationFrame(() => economyChart?.resize());
  if(ten === 'spatial') refreshSpatial();
  /* ECharts không đo được khung đang ẩn, nên phải vẽ lại sau khi màn hiện ra. */
  if(ten === 'chiso' && !$('o-chart').hidden) requestAnimationFrame(veDuong);
}

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
  thanh.addEventListener('dblclick', () => dat(268));
})();

/* ===================== bản đồ ===================== */
/* Hai mức sáng cho đường ranh giới. Khi xem toàn quốc thì đường viền chỉ là nền, phải mờ
   để không át ảnh đêm. Khi đã chọn một tỉnh thì người dùng cần thấy rõ ranh giới các tỉnh
   xung quanh để định vị, nên sáng hẳn lên. */
const VIEN = {
  mo:   {mau:'#3b4b6b', rong:0.6, dam:0.85},
  sang: {mau:'#9db4dd', rong:1.1, dam:1.0},
};

const kieuNen = () => ({version:8, sources:{}, layers:[
  {id:'nen', type:'background', paint:{'background-color':'#05070d'}}]});

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
    f => String(f.properties.province_code).padStart(2,'0') === maDangXem);
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
  const cu = $('nhac-mat-na');
  if(cu) cu.remove();
  if(!chu) return;
  $('canh-bao').insertAdjacentHTML('beforeend',
    `<div class="canh thieu" id="nhac-mat-na">${chu}</div>`);
}

async function dungBanDo(){
  if(typeof maplibregl === 'undefined'){
    themCanhBao('thieu', 'Không tải được thư viện bản đồ (MapLibre GL). '
      + 'Màn Chỉ số đêm vẫn hoạt động.');
    return;
  }
  banDo = new maplibregl.Map({container:'ban-do', style:kieuNen(),
    center:[106.0, 16.3], zoom:4.8, attributionControl:false});
  banDo.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');
  banDo.addControl(new maplibregl.ScaleControl({maxWidth:120, unit:'metric'}), 'bottom-right');
  await new Promise(ok => banDo.on('load', ok));

  try{ ranhGioi = await layJSON('/api/boundaries.geojson'); }
  catch{
    themCanhBao('thieu', 'Chưa có ranh giới tỉnh. Chạy: '
      + '<code>python -m backend.data.build_boundaries --tai-gadm</code>');
  }
  if(!ranhGioi) return;
  chuanHoaRanhGioi(ranhGioi);

  banDo.addSource('tinh', {type:'geojson', data:ranhGioi, promoteId:'province_code'});
  banDo.addSource('mat-na', {type:'geojson', data:{type:'FeatureCollection', features:[]}});
  /* Lớp bắt sự kiện bấm: trong suốt, nằm dưới ảnh và mặt nạ. */
  banDo.addLayer({id:'tinh-bat', type:'fill', source:'tinh',
    paint:{'fill-color':'#16203a','fill-opacity':0.001}});
  /* Che hẳn, không để lọt 10% ánh sáng của vùng ngoài ranh giới. */
  banDo.addLayer({id:'mat-na-lop', type:'fill', source:'mat-na',
    paint:{'fill-color':'#05070d','fill-opacity':1}});
  banDo.addLayer({id:'tinh-vien', type:'line', source:'tinh',
    paint:{'line-color':VIEN.mo.mau,'line-width':VIEN.mo.rong,'line-opacity':VIEN.mo.dam}});
  /* Quầng sáng mảnh dưới đường viền tỉnh đang chọn, để nó nổi trên nền ảnh đêm. */
  banDo.addLayer({id:'tinh-vien-quang', type:'line', source:'tinh',
    filter:['==','province_code',''],
    paint:{'line-color':'#ffc857','line-width':7,'line-opacity':0.22,'line-blur':4}});
  banDo.addLayer({id:'tinh-vien-dam', type:'line', source:'tinh',
    filter:['==','province_code',''],
    paint:{'line-color':'#ffd87a','line-width':2.4}});
  banDo.on('click','tinh-bat', e => {
    const ma = String(e.features[0].properties.province_code).padStart(2,'0');
    xoaBoLoc();
    $('chon-tinh').value = ma; applySharedContext(ma,demoSelection.year,demoSelection.month);
  });
  banDo.on('mouseenter','tinh-bat',()=>banDo.getCanvas().style.cursor='pointer');
  banDo.on('mouseleave','tinh-bat',()=>banDo.getCanvas().style.cursor='');
  banDo.fitBounds(bienDoTatCa(), {padding:30, duration:0});
  datMatNa();
}

function themCanhBao(loai, chu){
  $('canh-bao').insertAdjacentHTML('beforeend', `<div class="canh ${loai}">${chu}</div>`);
}

/* ===================== ảnh đêm ===================== */
function doiAnhNen(chiSo){
  const muc = cacMoc[chiSo];
  if(muc){ demoSelection.year = muc.year; demoSelection.month = muc.month || 0; syncContext(); }
  if(demoReady) refreshDemo();
  veThe(muc);
  if(!banDo) return;
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  if(!muc || !thongTinNen?.tiles){ dongThangMau(); return; }
  const nguon = {type:'raster', tileSize:256,
    tiles:[`${thongTinNen.tiles}${encodeURIComponent(muc.path)}`
           + `&rescale=0,60&colormap_name=inferno&nodata=-9999`]};
  /* Giới hạn theo phạm vi ảnh: thiếu nó thì bản đồ xin ô khắp thế giới và TiTiler
     trả 500 cho mọi ô nằm ngoài ảnh — hàng trăm lượt gọi hỏng mỗi lần mở trang. */
  if([muc.west, muc.south, muc.east, muc.north].every(v => typeof v === 'number')){
    nguon.bounds = [muc.west, muc.south, muc.east, muc.north];
  }
  banDo.addSource('anh-dem', nguon);
  /* Ảnh nằm DƯỚI mặt nạ, nên phần ngoài ranh giới bị che — ảnh hiện đúng trong ranh giới.
     Chưa có ranh giới thì lớp mặt nạ không tồn tại: chèn "trước" nó sẽ ném lỗi và ảnh
     không hiện chút nào. Khi đó cứ xếp ảnh lên trên cùng. */
  const truocLop = banDo.getLayer('mat-na-lop') ? 'mat-na-lop' : undefined;
  banDo.addLayer({id:'anh-dem', type:'raster', source:'anh-dem',
    paint:{'raster-opacity':1}}, truocLop);
  moThangMau(muc);
}

function moThangMau(muc){
  const donVi = muc.source === 'DMSP' ? 'DN 0–63' : 'nW/cm²/sr';
  $('thang-mau').style.display = '';
  $('thang-mau').innerHTML =
    `<b>0</b><span class="dai" style="background:linear-gradient(90deg,`
    + `#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4)"></span><b>60</b><span>${donVi}</span>`;
}
const dongThangMau = () => { $('thang-mau').style.display = 'none'; };

/* ===================== ba thẻ số liệu ===================== */
function theSo(nhan, gt, donVi){
  return `<div class="the"><div class="nhan">${nhan}</div>`
    + `<div class="hang"><span class="gt">${gt}</span>`
    + `<span class="dvi">${thoat(donVi)}</span></div></div>`;
}

let cardRequest = 0;
async function veThe(muc){
  const request = ++cardRequest;
  const o = $('the-so');
  if(!muc){
    o.innerHTML = theSo('SOL','—','') + theSo('Diện tích sáng','—','km²') + theSo('Mật độ','—','');
    $('nut-tai-anh').disabled = true;
    $('ghi-chu-tai').textContent = '';
    return;
  }
  $('nut-tai-anh').disabled = false;
  $('ghi-chu-tai').textContent = maDangXem
    ? 'GeoTIFF của tỉnh đang chọn, đã cắt theo ranh giới. Mở được bằng QGIS.'
    : 'GeoTIFF toàn quốc của mốc đang chọn. Mở được bằng QGIS.';
  const donVi = muc.source === 'DMSP' ? 'DN' : 'nW/cm²/sr';
  let sol = null, dienTich = null, matDo = null;
  try{
    if(maDangXem){
      const d = await layJSON('/api/panel?chi_so=sol,lit_area_km2,sol_density'
        + `&moc=${maMoc(muc)}&province_code=${maDangXem}`);
      const lay = ma => (d.dong.find(r => r.chi_so === ma) || {}).gia_tri?.[0];
      sol = lay('sol'); dienTich = lay('lit_area_km2'); matDo = lay('sol_density');
    }else{
      const d = await layJSON(`/api/tong-hop?nam=${muc.year}&thang=${muc.month || 0}`);
      sol = d.sol; dienTich = d.lit_area_km2; matDo = d.sol_density;
    }
  }catch{ /* chưa có chỉ số của mốc này — ba thẻ để gạch ngang, không bịa số */ }
  if(request !== cardRequest) return;
  o.innerHTML =
      theSo('SOL', dinhDang(sol, 0) ?? '—', sol === null || sol === undefined ? '' : donVi)
    + theSo('Diện tích sáng', dinhDang(dienTich, 0) ?? '—', 'km²')
    + theSo('Mật độ', dinhDang(matDo, 2) ?? '—',
            matDo === null || matDo === undefined ? '' : 'trên km²');
}

function chonPhamVi(ma){
  maDangXem = ma || null;
  demoSelection.code = maDangXem;
  syncContext();
  if(demoReady) refreshDemo();
  const ten = ma ? (danhSachTinh.find(t => t.province_code === ma) || {}).province_name
                 : 'Toàn quốc';
  $('nhan-pham-vi').textContent = ten || 'Toàn quốc';
  veThe(cacMoc[Number($('chon-nam').value)]);
  if(!banDo || !ranhGioi) return;
  datMatNa();
  const kieu = ma ? VIEN.sang : VIEN.mo;
  banDo.setPaintProperty('tinh-vien', 'line-color', kieu.mau);
  banDo.setPaintProperty('tinh-vien', 'line-width', kieu.rong);
  banDo.setPaintProperty('tinh-vien', 'line-opacity', kieu.dam);
  banDo.setFilter('tinh-vien-dam', ['==','province_code', ma || '']);
  banDo.setFilter('tinh-vien-quang', ['==','province_code', ma || '']);
  const f = ma && ranhGioi.features.find(
    x => String(x.properties.province_code).padStart(2,'0') === ma);
  banDo.fitBounds(f ? bienDo(f) : bienDoTatCa(),
                  {padding: f ? 60 : 30, duration:600, maxZoom:10});
}

function dungDanhSachTinh(ds){
  $('chon-tinh').innerHTML = '<option value="">Toàn quốc</option>'
    + ds.map(t => `<option value="${t.province_code}">${thoat(t.province_name)}</option>`).join('');
}

/* Bộ lọc đang bật mà chọn tỉnh từ bản đồ thì ô chọn hiện trống vì option bị ẩn. */
function xoaBoLoc(){
  const o = $('tim-tinh');
  if(o) o.value = '';
  locTinh('');
}

function locTinh(tu){
  const tim = khongDau(tu);
  let con = 0;
  for(const o of $('chon-tinh').options){
    const hop = !o.value || !tim || khongDau(o.textContent).includes(tim);
    o.hidden = !hop;
    if(hop && o.value) con++;
  }
  $('khong-thay-tinh').classList.toggle('an', con > 0 || !tim);
  // Còn đúng một tỉnh thì chọn luôn: đó là điều người gõ đang muốn.
  if(con === 1){
    const mot = [...$('chon-tinh').options].find(o => !o.hidden && o.value);
    if($('chon-tinh').value !== mot.value){ $('chon-tinh').value = mot.value; chonPhamVi(mot.value); }
  }
}

let timelineRequest = 0;
async function napMoc(buocMoi, preferred = null){
  const request = ++timelineRequest;
  buoc = buocMoi;
  document.querySelectorAll('.buoc').forEach(b =>
    b.classList.toggle('dang-chon', b.dataset.buoc === buoc));
  let data;
  try{ data = await layJSON(`/api/basemap?buoc=${buocMoi}${demoSelection.code ? '&province_code='+encodeURIComponent(demoSelection.code):''}`); }
  catch{ data = null; }
  if(request !== timelineRequest) return;
  thongTinNen = data;
  cacMoc = thongTinNen?.chi_tiet || [];

  const chon = $('chon-nam'), truot = $('nam-truot');
  nhacThoiGian(null);
  if(!cacMoc.length){
    chon.innerHTML = '<option>— chưa có ảnh —</option>';
    chon.disabled = truot.disabled = true;
    doiAnhNen(-1);
    nhacThoiGian('Chưa có sổ ảnh cho mốc này trong database đang mở. Kiểm tra dữ liệu đã nạp hoặc phục hồi bản P1 đã kiểm chứng; không cần tạo lại ảnh ngay.');
    return;
  }
  chon.disabled = truot.disabled = false;
  /* Giá trị của ô chọn và thanh trượt là CHỈ SỐ trong mảng mốc, không phải năm:
     ở chế độ tháng các mốc cách nhau một tháng, không đều theo năm. */
  chon.innerHTML = cacMoc.map((m, i) => `<option value="${i}">${tenMoc(m)}</option>`)
    .reverse().join('');
  const index = preferred ? cacMoc.findIndex(m => maMoc(m) === preferred) : cacMoc.length - 1;
  if(index < 0){
    chon.insertAdjacentHTML('afterbegin', '<option value="">— chưa có COG ở mốc đã chọn —</option>');
    chon.value = ''; truot.disabled = true; doiAnhNen(-1);
  }else{
    truot.min = 0; truot.max = cacMoc.length - 1; truot.value = index;
    chon.value = index; doiAnhNen(index);
  }
  if(buoc === 'thang' && thongTinNen.ghi_chu_thang) nhacThoiGian(thongTinNen.ghi_chu_thang);
}

function nhacThoiGian(chu){
  const cu = $('nhac-thoi-gian');
  if(cu) cu.remove();
  if(!chu) return;
  $('canh-bao').insertAdjacentHTML('beforeend',
    `<div class="canh" id="nhac-thoi-gian">${chu}</div>`);
}

/* ===================== màn 2: bảng điều khiển lọc ===================== */
/* Theo mẫu World Bank DataBank: bốn nhóm gập mở, mỗi nhóm hiện "Có N · Chọn n",
   chọn bằng ô tick vì người dùng cần nhiều tỉnh, nhiều chỉ số, nhiều mốc cùng lúc. */
const NAM_DAU = 2004, NAM_CUOI = 2025, NAM_CO_THANG = 2014;
const chon = {tinh:new Set(), chiSo:new Set(['sol']), moc:new Set(), ham:new Set()};
const HAM = {tong:'Tổng trong khoảng', trung_binh:'Trung bình trong khoảng',
             thay_doi:'Thay đổi toàn kỳ (%)', cagr:'Tốc độ tăng trưởng bình quân năm (%)'};

function nhomLoc(ten, id, than, mo){
  return `<details class="nhom"${mo ? ' open' : ''}>
    <summary>${ten}<span class="dem" id="dem-${id}"></span></summary>
    <div class="than-nhom">${than}</div></details>`;
}

function congCu(id, goi){
  return `<div class="cong-cu">
    <button type="button" data-tat-ca="${id}" title="Chọn tất cả">✓</button>
    <button type="button" data-bo-het="${id}" title="Bỏ chọn tất cả">✕</button>
    <input type="search" data-tim="${id}" placeholder="${goi}" aria-label="${goi}"></div>`;
}

function dsTinhLoc(){
  const li = danhSachTinh.map(t =>
    `<li><label><input type="checkbox" data-tinh="${t.province_code}" checked>`
    + `<span>${thoat(t.province_name)}</span></label></li>`).join('');
  return congCu('tinh', 'tìm tỉnh…') + `<ul class="ds" id="ds-tinh">${li}</ul>`;
}

function dsChiSoLoc(){
  /* Trước đây lọc bỏ mọi chỉ số thuộc bảng economy, nên GRDP không bao giờ
     hiện trong bộ lọc. Nay bày cả: chúng chỉ có theo năm, và chế độ xem tháng trả về
     trống chứ không lặp lại số của năm. */
  const li = danhMuc.map(e =>
    `<li><label><input type="checkbox" data-chiso="${e.ma}"`
    + `${chon.chiSo.has(e.ma) ? ' checked' : ''}>`
    + `<span>${thoat(e.ten)} <span class="dv">(${thoat(e.don_vi)})</span></span>`
    + `</label></li>`).join('');
  return congCu('chiso', 'tìm chỉ số…') + `<ul class="ds" id="ds-chiso">${li}</ul>`;
}

function cayThoiGian(){
  const hang = [];
  for(let y = NAM_CUOI; y >= NAM_DAU; y--){
    const o = `<input type="checkbox" data-nam="${y}" id="y${y}">`;
    if(y >= NAM_CO_THANG){
      const th = THANG_VN.map(m =>
        `<label><input type="checkbox" data-thang="${y}-${m}">${m}</label>`).join('');
      hang.push(`<li><div class="nam-hang">${o}<label for="y${y}">${y}</label>`
        + `<span class="dem-thang" data-dem-thang="${y}"></span>`
        + `<button class="mo-thang" type="button" aria-expanded="false"`
        + ` aria-label="Mở 12 tháng của năm ${y}">▸</button></div>`
        + `<div class="thang-luoi" hidden>${th}`
        + `<button type="button" class="ca-nam" data-thang-nam="${y}">cả 12 tháng</button>`
        + `</div></li>`);
    }else{
      hang.push(`<li><div class="nam-hang">${o}<label for="y${y}">${y}</label></div></li>`);
    }
  }
  return `<p class="canh-nho">Khoảng có sẵn: <b>${NAM_DAU}–${NAM_CUOI}</b> · theo tháng chỉ`
    + ` từ ${NAM_CO_THANG}. DMSP là ảnh tổng hợp năm, NOAA không phát hành theo tháng.<br>`
    + `Tick vào <b>năm</b> là lấy dòng theo năm; muốn xem theo tháng thì mở mũi tên ▸ và`
    + ` tick từng tháng. Hai loại dòng này mang những chỉ số khác nhau.</p>`
    + `<p class="nhanh">XEM GẦN ĐÂY ${[5,10,15,20].map(n =>
        `<button type="button" data-gan-day="${n}">${n}</button>`).join('')}</p>`
    + `<ul class="cay" id="cay-thoi-gian">${hang.join('')}</ul>`;
}

function dsHam(){
  return `<ul class="ds" id="ds-ham">` + Object.entries(HAM).map(([ma, ten]) =>
    `<li><label><input type="checkbox" data-ham="${ma}"><span>${ten}</span></label></li>`
  ).join('') + '</ul>'
  + '<p class="canh-nho">Mỗi hàm thành một cột phụ bên phải bảng. Tốc độ tăng trưởng và '
  + 'thay đổi toàn kỳ từ chối chạy khi khoảng bắc qua mốc đổi vệ tinh.</p>';
}

function dungLoc(hop){
  hop.innerHTML =
      nhomLoc('Phạm vi', 'tinh', dsTinhLoc(), false)
    + nhomLoc('Chỉ số', 'chiso', dsChiSoLoc(), true)
    + nhomLoc('Thời gian', 'moc', cayThoiGian(), true)
    + nhomLoc('Hàm thời gian', 'ham', dsHam(), false);
  danhSachTinh.forEach(t => chon.tinh.add(t.province_code));
  for(let y = NAM_CUOI - 5; y <= NAM_CUOI; y++) chon.moc.add(String(y));
  dongBoCay(hop);
  capNhatDem(hop);

  hop.addEventListener('change', e => {
    const o = e.target;
    if(o.dataset.tinh)  o.checked ? chon.tinh.add(o.dataset.tinh)  : chon.tinh.delete(o.dataset.tinh);
    if(o.dataset.chiso) o.checked ? chon.chiSo.add(o.dataset.chiso): chon.chiSo.delete(o.dataset.chiso);
    if(o.dataset.ham)   o.checked ? chon.ham.add(o.dataset.ham)    : chon.ham.delete(o.dataset.ham);
    /* Mốc năm và mốc tháng là HAI dòng dữ liệu khác nhau, không phải cha–con:
       dòng năm có month = 0 và mang những chỉ số chỉ tính theo năm (sol_change_pct),
       dòng tháng mang những chỉ số chỉ tính theo tháng (sol_change_mom_pct, sol_ma3).
       Vì vậy tick năm KHÔNG kéo theo 12 tháng — làm thế thì chọn một chỉ số theo năm
       sẽ ra bảng trống toàn dấu gạch. Muốn xem tháng thì mở mũi tên và tick tháng. */
    if(o.dataset.nam){
      o.checked ? chon.moc.add(o.dataset.nam) : chon.moc.delete(o.dataset.nam);
    }
    if(o.dataset.thang){
      o.checked ? chon.moc.add(o.dataset.thang) : chon.moc.delete(o.dataset.thang);
      danhDauCoThang(hop, o.dataset.thang.slice(0,4));
    }
    capNhatDem(hop); napBang();
    if((o.dataset.tinh || o.dataset.nam || o.dataset.thang) && chon.tinh.size === 1 && chon.moc.size === 1) adoptPanelContext();
  });

  hop.addEventListener('click', e => {
    const n = e.target.closest('button');
    if(!n) return;
    if(n.classList.contains('mo-thang')){
      const luoi = n.closest('li').querySelector('.thang-luoi');
      const mo = luoi.hidden;
      luoi.hidden = !mo;
      n.setAttribute('aria-expanded', String(mo));
      n.textContent = mo ? '▾' : '▸';
      return;
    }
    if(n.dataset.ganDay){
      const n2 = Number(n.dataset.ganDay);
      chon.moc.clear();
      hop.querySelectorAll('[data-thang]').forEach(t => { t.checked = false; });
      hop.querySelectorAll('[data-nam]').forEach(t => {
        const y = Number(t.dataset.nam);
        t.checked = y > NAM_CUOI - n2;
        if(t.checked) chon.moc.add(t.dataset.nam);
      });
      hop.querySelectorAll('[data-nam]').forEach(t => danhDauCoThang(hop, t.dataset.nam));
      capNhatDem(hop); napBang(); return;
    }
    if(n.dataset.thangNam){                       // "chọn cả 12 tháng" của một năm
      const y = n.dataset.thangNam;
      const con = [...hop.querySelectorAll(`[data-thang^="${y}-"]`)];
      const bat = !con.every(t => t.checked);
      con.forEach(t => {
        t.checked = bat;
        bat ? chon.moc.add(t.dataset.thang) : chon.moc.delete(t.dataset.thang);
      });
      danhDauCoThang(hop, y);
      capNhatDem(hop); napBang(); return;
    }
    const tatCa = n.dataset.tatCa, boHet = n.dataset.boHet;
    if(!tatCa && !boHet) return;
    const loai = tatCa || boHet;
    const bat = Boolean(tatCa);
    hop.querySelectorAll(`#ds-${loai} input`).forEach(o => {
      if(o.closest('li').hidden) return;
      o.checked = bat;
      const kho = loai === 'tinh' ? chon.tinh : chon.chiSo;
      const ma = o.dataset.tinh || o.dataset.chiso;
      bat ? kho.add(ma) : kho.delete(ma);
    });
    capNhatDem(hop); napBang();
  });

  hop.addEventListener('input', e => {
    const loai = e.target.dataset?.tim;
    if(!loai) return;
    const tim = khongDau(e.target.value);
    hop.querySelectorAll(`#ds-${loai} li`).forEach(li => {
      li.hidden = Boolean(tim) && !khongDau(li.textContent).includes(tim);
    });
  });
}

function dongBoCay(hop){
  hop.querySelectorAll('[data-nam]').forEach(o => {
    o.checked = chon.moc.has(o.dataset.nam);
    danhDauCoThang(hop, o.dataset.nam);
  });
  hop.querySelectorAll('[data-thang]').forEach(o => o.checked = chon.moc.has(o.dataset.thang));
}

/* Ô tick năm không còn phản ánh trạng thái các tháng, nên phải có chỗ khác cho biết
   năm này đang chọn mấy tháng — nếu không, tháng đã tick rồi gập lại là mất dấu. */
function danhDauCoThang(hop, nam){
  const o = hop.querySelector(`[data-dem-thang="${nam}"]`);
  if(!o) return;
  const so = [...hop.querySelectorAll(`[data-thang^="${nam}-"]`)].filter(t => t.checked).length;
  o.textContent = so ? `${so} tháng` : '';
  o.hidden = !so;
}

function capNhatDem(hop){
  const dat = (id, co, da) => {
    const o = hop.querySelector(`#dem-${id}`);
    if(o) o.innerHTML = `Có <b>${co}</b> · Chọn <b>${da}</b>`;
  };
  dat('tinh', danhSachTinh.length, chon.tinh.size);
  dat('chiso', hop.querySelectorAll('[data-chiso]').length, chon.chiSo.size);
  dat('moc', (NAM_CUOI - NAM_DAU + 1) + (NAM_CUOI - NAM_CO_THANG + 1) * 12, chon.moc.size);
  const oHam = hop.querySelector('#dem-ham');
  if(oHam) oHam.innerHTML = `Đã thêm <b>${chon.ham.size}</b>`;
}

/* ===================== màn 2: bảng và biểu đồ ===================== */
let duLieuBang = null;

function thamSoBang(){
  const sapXep = a => [...a].sort();
  const p = new URLSearchParams();
  p.set('chi_so', sapXep(chon.chiSo).join(','));
  if(chon.moc.size) p.set('moc', sapXep(chon.moc).join(','));
  if(chon.tinh.size && chon.tinh.size < danhSachTinh.length)
    p.set('province_code', sapXep(chon.tinh).join(','));
  if(chon.ham.size) p.set('ham', sapXep(chon.ham).join(','));
  return p;
}

async function napBang(){
  const o = $('canh-bao-bang');
  if(!chon.chiSo.size || !chon.moc.size){
    duLieuBang = null;
    $('bang-chiso').innerHTML = '';
    o.innerHTML = '<div class="canh">Chọn ít nhất một chỉ số và một mốc thời gian.</div>';
    return;
  }
  try{ duLieuBang = await layJSON('/api/panel?' + thamSoBang()); }
  catch(loi){
    o.innerHTML = `<div class="canh thieu">Không lấy được số liệu: ${thoat(loi.message)}</div>`;
    return;
  }
  o.innerHTML = (duLieuBang.canh_bao || [])
    .map(c => `<div class="canh">${thoat(c)}</div>`).join('');
  veBang();
  if(!$('o-chart').hidden) veDuong();
}

function veBang(){
  const d = duLieuBang;
  if(!d) return;
  const chuSo = {};
  d.chi_so.forEach(e => { chuSo[e.ma] = e.chu_so; });
  /* API trả theo mã thống kê (bắc xuống nam). Bảng phải xếp A-Z như bộ chọn phạm vi,
     và trong mỗi tỉnh giữ nguyên thứ tự chỉ số. */
  const thuTuChiSo = new Map(d.chi_so.map((e, i) => [e.ma, i]));
  const dong = [...d.dong].sort((a, b) =>
    a.province_name.localeCompare(b.province_name, 'vi')
    || thuTuChiSo.get(a.chi_so) - thuTuChiSo.get(b.chi_so));
  let truoc = null;
  const than = dong.map(r => {
    const dau = r.province_code === truoc ? '' : thoat(r.province_name);
    truoc = r.province_code;
    /* Bảng không in chữ cờ. Nghĩa của cờ nằm ở tooltip; chú giải đầy đủ đi kèm
       tệp tải xuống. */
    const chuGiai = d.chu_giai_co || {};
    const o = r.gia_tri.map((v, i) => {
      const co = (r.co || [])[i];
      const tt = co && chuGiai[co] ? ` title="${thoat(chuGiai[co])}"` : '';
      return (v === null || v === undefined)
        ? `<td class="rong" title="Chưa có dữ liệu hoặc chỉ số không áp dụng ở mốc này">—</td>`
        : `<td${tt}>${dinhDang(v, chuSo[r.chi_so] ?? 2)}</td>`;
    }).join('')
    + (d.ham || []).map(h => {
        const v = (r.ham || {})[h.ma];
        if(v !== null && v !== undefined) return `<td class="ham-o">${dinhDang(v, 2)}</td>`;
        const vi = r.ham_tu_choi
          ? ` title="Không tính được: ${thoat(r.ham_tu_choi.join('; '))}"` : '';
        return `<td class="rong ham-o"${vi}>—</td>`;
      }).join('');
    return `<tr class="${r.province_code === maDangXem ? 'sang' : ''}">`
      + `<td>${dau}</td><td>${thoat(r.ten)}</td>${o}</tr>`;
  }).join('');
  $('bang-chiso').innerHTML =
    `<thead><tr><th>Tỉnh</th><th>Chỉ số</th>`
    + d.moc.map(m => `<th>${m}</th>`).join('')
    + (d.ham || []).map(h => `<th class="ham-o">${thoat(h.ten)}</th>`).join('')
    + '</tr></thead>'
    + `<tbody>${than}</tbody>`;
}

const MAU = ['#ffc857','#6aa9ff','#7ddc8a','#ff7b72','#c792ea','#ffa07a','#7fd1d1','#f6a1c0'];
let bieuDo = null;
const TOI_DA_DUONG = 8;

function veDuong(){
  const d = duLieuBang;
  const khung = $('bd-duong');
  if(!d || typeof echarts === 'undefined'){
    $('ghi-bd').textContent = typeof echarts === 'undefined'
      ? 'Không tải được thư viện biểu đồ (ECharts).' : '';
    return;
  }
  bieuDo = bieuDo || echarts.init(khung);
  /* Quá 8 đường thì chồng nhau, vô dụng: chỉ vẽ tỉnh đang chọn, và nói rõ đã bỏ bao nhiêu. */
  let dong = [...d.dong].sort((a, b) => a.province_name.localeCompare(b.province_name, 'vi'));
  let ghi = 'Khoảng đứt là mốc không có số liệu, không nối qua.';
  if(dong.length > TOI_DA_DUONG){
    const giu = maDangXem ? dong.filter(r => r.province_code === maDangXem) : [];
    dong = (giu.length ? giu : dong.slice(0, TOI_DA_DUONG));
    ghi = `Đang chọn ${d.dong.length} chuỗi, quá ${TOI_DA_DUONG} đường thì chồng nhau nên chỉ `
      + `vẽ ${dong.length}. Bỏ bớt tick ở cột trái để xem chuỗi khác. ` + ghi;
  }
  $('ghi-bd').textContent = ghi;
  bieuDo.setOption({
    animationDuration: 400,
    textStyle:{color:'#8b97b0'},
    /* Chú giải có thể dài hai dòng khi tên tỉnh ghép với tên chỉ số: chừa chỗ cho nó,
       nếu không nó đè lên đỉnh biểu đồ. */
    grid:{left:64, right:18, top:72, bottom:34},
    tooltip:{trigger:'axis', backgroundColor:'#131b2d', borderColor:'#232e45',
             textStyle:{color:'#e8ecf5'}},
    legend:{top:0, type:'scroll', textStyle:{color:'#8b97b0'}, icon:'roundRect',
            itemWidth:12, itemHeight:3, pageIconColor:'#8b97b0',
            pageTextStyle:{color:'#8b97b0'},
            data:dong.map(r => `${r.province_name} · ${r.ten}`)},
    xAxis:{type:'category', data:d.moc, boundaryGap:false,
           axisLine:{lineStyle:{color:'#232e45'}}, axisTick:{show:false},
           /* 2010 và 2014 là mốc đổi vệ tinh: không cắt đường, chỉ đánh dấu ở trục. */
           axisLabel:{color:v => (v === '2010' || v === '2014') ? '#ffc857' : '#8b97b0'}},
    yAxis:{type:'value', axisLine:{lineStyle:{color:'#232e45'}}, axisTick:{show:false},
           splitLine:{lineStyle:{color:'#1a2334'}},
           axisLabel:{formatter:v => Number(v).toLocaleString('vi-VN')}},
    series:dong.map((r, i) => ({
      name:`${r.province_name} · ${r.ten}`, type:'line', connectNulls:false,
      smooth:false, color:MAU[i % MAU.length], lineStyle:{width:2},
      showSymbol:d.moc.length <= 36, symbolSize:6,
      /* Điểm mang cờ U vẽ rỗng ruột: giữ số mà vẫn nói rằng điểm đó kém tin cậy. */
      data:r.gia_tri.map((v, k) => ((r.co || [])[k] === 'U' && v !== null)
        ? {value:v, itemStyle:{color:'#080c16', borderColor:MAU[i % MAU.length],
                               borderWidth:2}}
        : v)})),
  }, true);
  bieuDo.resize();
}

function doiXem(mode){
  $('o-bang').hidden = mode!=='bang';
  $('o-chart').hidden = mode!=='chart';
  document.querySelectorAll('#xem-chiso button').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.xem===mode)));
  if(mode==='chart') requestAnimationFrame(veDuong);
}

/* ===================== màn 3: chỉ số kinh tế đêm ===================== */


/* ===================== khởi động ===================== */
(async function khoiDong(){
  document.querySelectorAll('.thanh-man button').forEach(b => {
    b.onclick = () => chuyenMan(b.dataset.man);
  });

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
  // API trả theo mã thống kê (bắc xuống nam). Cô dặn danh sách phải xếp A-Z,
  // nên sắp lại ở đây chứ không đổi thứ tự của API — nơi khác còn dựa vào mã.
  danhSachTinh.sort((a, b) => a.province_name.localeCompare(b.province_name, 'vi'));
  dungDanhSachTinh(danhSachTinh);
  // /api/indicators bọc danh sách trong {chi_so: [...]}
  try{ danhMuc = (await layJSON('/api/indicators')).chi_so || []; }catch{ danhMuc = []; }
  chon.chiSo=new Set(danhMuc.filter(e=>e.bang!=='economy').map(e=>e.ma));

  $('chon-tinh').onchange = () => applySharedContext($('chon-tinh').value,demoSelection.year,demoSelection.month);
  $('tim-tinh').oninput = () => locTinh($('tim-tinh').value);
  // Enter chọn luôn tỉnh đầu tiên còn lại, để gõ xong không phải với chuột.
  $('tim-tinh').onkeydown = e => {
    if(e.key !== 'Enter') return;
    const con = [...$('chon-tinh').options].filter(o => !o.hidden && o.value);
    if(con.length){ $('chon-tinh').value = con[0].value; applySharedContext(con[0].value,demoSelection.year,demoSelection.month); }
  };
  $('nut-toan-quoc').onclick = () => { xoaBoLoc(); $('chon-tinh').value = ''; applySharedContext('',demoSelection.year,demoSelection.month); };
  $('nut-tai-anh').onclick = () => {
    const muc = cacMoc[Number($('chon-nam').value)];
    if(!muc) return;
    const tinh = maDangXem ? `&province_code=${maDangXem}` : '';
    window.location = `/api/anh-dem.tif?nam=${muc.year}&thang=${muc.month || 0}${tinh}`;
  };

  const oChon = $('chon-nam'), truot = $('nam-truot');
  const applyTime = index => { const m=cacMoc[index]; if(m) applySharedContext(demoSelection.code,m.year,m.month || 0); };
  oChon.onchange = () => applyTime(Number(oChon.value));
  let slideTimer;
  truot.oninput = () => { oChon.value=truot.value; clearTimeout(slideTimer); slideTimer=setTimeout(()=>applyTime(Number(truot.value)),120); };
  document.querySelectorAll('.buoc').forEach(b => {
    b.onclick = () => { if(b.dataset.buoc !== buoc) applySharedContext(demoSelection.code,demoSelection.year,b.dataset.buoc === 'nam' ? 0 : (demoSelection.month || 1)); };
  });

  dungLoc($('loc-chiso'));
  document.querySelectorAll('#xem-chiso button').forEach(b => {
    b.onclick = () => doiXem(b.dataset.xem);
  });
  $('nut-csv').onclick = () => { window.location = '/api/panel.csv?' + thamSoBang(); };
  addEventListener('resize', () => { bieuDo?.resize(); economyChart?.resize(); });

  await dungBanDo();
  chonPhamVi(null);
  await napMoc('nam');
  const co = thongTinNen?.co_san || {};
  document.querySelectorAll('.buoc').forEach(b => { b.disabled = !co[b.dataset.buoc]; });
  if(!co.nam && co.thang) await napMoc('thang');
  if(!thongTinNen?.tiles && (co.nam || co.thang)){
    themCanhBao('thieu', 'Có ảnh nhưng chưa cài TiTiler nên chưa phục vụ được ô bản đồ: '
      + '<code>pip install -r backend/requirements.txt</code>');
  }
  await napBang();
  initDemoContext();
  demoReady = true;
  await applySharedContext('01', 2024, 0);
})();
