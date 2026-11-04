'use strict';
/* VNGISDash — giao diện nguyên mẫu.
   Nguyên tắc: thiếu dữ liệu thì nói rõ là thiếu, không bao giờ vẽ số giả. */

const API = '';
const KHONG_CO = 'chưa có số liệu';

const trangThai = document.getElementById('trang-thai');
const chonTinh  = document.getElementById('chon-tinh');
const namTu     = document.getElementById('nam-tu');
const namDen    = document.getElementById('nam-den');
const theSoLieu = document.getElementById('the-so-lieu');
const khungCanh = document.getElementById('canh-bao');
const nutExport = document.getElementById('nut-export');
const namNen    = document.getElementById('nam-nen');
const namNenHien= document.getElementById('nam-nen-hien');
const nenGhiChu = document.getElementById('nen-ghi-chu');

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
  const o = document.getElementById(id);
  if(typeof echarts === 'undefined'){
    /* Thư viện biểu đồ tải không được (mạng chặn CDN): nói ra, đừng để trang trống. */
    o.innerHTML = '<p class="ghi-chu">Không tải được thư viện biểu đồ (ECharts). '
      + 'Số liệu vẫn xem được ở bảng bên phải và trong file tải về.</p>';
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
    yAxis: haiTruc
      ? [{...THEME.yAxis}, {...THEME.yAxis, splitLine:{show:false}}]
      : THEME.yAxis,
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

function so(v, chuSo = 2){
  if(v === null || v === undefined || Number.isNaN(v)) return null;
  return Number(v.toFixed(chuSo));
}

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

async function layJSON(duongDan){
  const phanHoi = await fetch(API + duongDan);
  if(!phanHoi.ok) throw new Error(`${duongDan} → ${phanHoi.status}`);
  return phanHoi.json();
}

async function veTinh(){
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

  const namDem  = d.dem.map(r => r.nam);
  const namNgay = d.ngay.map(r => r.nam);
  veBieuDo('bd-dem', namDem,
    [{name:'Tổng độ sáng (SOL)', data:d.dem.map(r => so(r.sol_ntl))}], ['#ffc857']);
  veBieuDo('bd-dien-tich', namDem,
    [{name:'Số điểm ảnh sáng', data:d.dem.map(r => so(r.lit_pixels, 0))},
     {name:'Mật độ sáng',      data:d.dem.map(r => so(r.mat_do_ntl, 3))}],
    ['#5ec8d8','#7ddc8a'], true);
  veBieuDo('bd-ngay', namNgay,
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
  if(d.thieu_du_lieu.ngay)
    canh.push(['thieu','Chưa có chỉ số ảnh ngày cho tỉnh này.']);
  if(d.thieu_du_lieu.kinh_te)
    canh.push(['thieu','Chưa có dữ liệu dân số và GDP — chờ giảng viên cung cấp.']);
  (d.canh_bao || []).filter(v => !v.startsWith('SỐ LIỆU GIẢ LẬP'))
    .forEach(v => canh.push(['', v]));
  khungCanh.innerHTML = canh.map(([l,v]) => `<div class="canh ${l}">${v}</div>`).join('');

  nutExport.disabled = false;
  nutExport.onclick = () => {
    window.location = `${API}/api/export.zip?ma_tinh=${ma}&nam_tu=${tu}&nam_den=${den}`;
  };
}

/* ---- bản đồ nền ban đêm ---- */
let banDo, namCoAnh = [];

function kieuNen(){
  /* Không dùng dịch vụ bản đồ ngoài: nền là màu tối, lớp thông tin là ảnh đêm của chính
     dự án. Nhẹ, không cần khoá API, và đúng tinh thần "bản đồ nền ban đêm làm chủ đạo". */
  return {version:8, sources:{}, layers:[{id:'nen', type:'background',
          paint:{'background-color':'#05070d'}}]};
}

let coRanhGioi = true;

function bienBaoBanDo(){
  if(coRanhGioi || namCoAnh.length) return;
  document.getElementById('khung-ban-do').classList.add('trong');
}

async function dungBanDo(){
  if(typeof maplibregl === 'undefined'){
    nenGhiChu.textContent = 'Không tải được thư viện bản đồ (MapLibre GL). '
      + 'Phần chỉ số và nút tải dữ liệu vẫn hoạt động bình thường.';
    namNen.disabled = true;
    return;
  }
  banDo = new maplibregl.Map({container:'ban-do', style:kieuNen(),
    center:[106.0, 16.3], zoom:4.6, attributionControl:false});
  banDo.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');
  banDo.on('load', async () => {
    try{
      const gj = await layJSON('/api/boundaries.geojson');
      banDo.addSource('tinh', {type:'geojson', data:gj});
      banDo.addLayer({id:'tinh-to', type:'fill', source:'tinh',
        paint:{'fill-color':'#5ec8d8','fill-opacity':
          ['case',['boolean',['feature-state','chon'],false],0.22,0.04]}});
      banDo.addLayer({id:'tinh-vien', type:'line', source:'tinh',
        paint:{'line-color':'#2f3d5c','line-width':0.8}});
      banDo.on('click','tinh-to', e => {
        const ma = e.features[0].properties.ma_tinh;
        if(ma){ chonTinh.value = String(ma).padStart(2,'0'); veTinh(); }
      });
      banDo.on('mouseenter','tinh-to',()=>banDo.getCanvas().style.cursor='pointer');
      banDo.on('mouseleave','tinh-to',()=>banDo.getCanvas().style.cursor='');
    }catch{
      coRanhGioi = false;
      nenGhiChu.textContent = 'Chưa có ranh giới tỉnh để vẽ (cần GADM 4.1). ' +
        'Bản đồ vẫn chạy, chọn tỉnh bằng danh sách bên phải.';
    }
    await napAnhNen();
    bienBaoBanDo();
  });
}

async function napAnhNen(){
  let b;
  try{ b = await layJSON('/api/basemap'); }
  catch{ nenGhiChu.textContent = 'Chưa có ảnh nền ban đêm.'; return; }
  namCoAnh = b.nam || [];
  if(!namCoAnh.length || !b.tiles){
    nenGhiChu.textContent = namCoAnh.length
      ? 'Có ảnh nền nhưng chưa cài TiTiler nên chưa phục vụ được ô bản đồ.'
      : 'Chưa có ảnh nền ban đêm. Chạy: python3 -m app.data.build_cogs';
    namNen.disabled = true;
    return;
  }
  namNen.min = Math.min(...namCoAnh);
  namNen.max = Math.max(...namCoAnh);
  namNen.value = namNen.max;
  doiAnhNen(Number(namNen.value), b);
  namNen.oninput = () => doiAnhNen(Number(namNen.value), b);
}

function doiAnhNen(nam, b){
  namNenHien.textContent = nam;
  const muc = b.chi_tiet.find(c => c.nam === nam);
  if(!muc){ nenGhiChu.textContent = `Không có ảnh năm ${nam}.`; return; }
  nenGhiChu.textContent = `Ảnh đêm ${nam} · ${muc.nguon_anh || ''}`;
  if(banDo.getLayer('anh-dem')) banDo.removeLayer('anh-dem');
  if(banDo.getSource('anh-dem')) banDo.removeSource('anh-dem');
  banDo.addSource('anh-dem', {type:'raster', tileSize:256,
    tiles:[`${b.tiles}${encodeURIComponent(muc.duong_dan)}&rescale=0,60&colormap_name=inferno`]});
  banDo.addLayer({id:'anh-dem', type:'raster', source:'anh-dem',
    paint:{'raster-opacity':0.9}}, banDo.getLayer('tinh-to') ? 'tinh-to' : undefined);
}

/* ---- khởi động ---- */
(async function khoiDong(){
  try{
    const suc = await layJSON('/api/health');
    trangThai.textContent = suc.ok ? `${suc.so_tinh} tỉnh` : 'chưa có dữ liệu';
    document.body.classList.toggle('co-gia-lap', false);
    trangThai.className = 'pill ' + (suc.ok ? 'ok' : 'loi');
  }catch{
    trangThai.textContent = 'API không phản hồi';
    trangThai.className = 'pill loi';
    return;
  }
  const {tinh} = await layJSON('/api/provinces');
  chonTinh.innerHTML = tinh.map(t => {
    const co = t.so_nam_dem || t.so_nam_ngay;
    return `<option value="${t.ma_tinh}">${t.ten_tinh}${co ? '' : ' — chưa có số liệu'}</option>`;
  }).join('');
  const dauTien = tinh.find(t => t.so_nam_dem || t.so_nam_ngay) || tinh[0];
  chonTinh.value = dauTien.ma_tinh;
  chonTinh.onchange = veTinh;
  namTu.onchange = veTinh;
  namDen.onchange = veTinh;
  await veTinh();
  try{
    await dungBanDo();
  }catch(loi){
    nenGhiChu.textContent = 'Bản đồ không khởi tạo được: ' + loi.message
      + '. Phần chỉ số vẫn hoạt động.';
  }
  window.addEventListener('resize', () => Object.values(bieuDo).forEach(b => b.resize()));
})();
