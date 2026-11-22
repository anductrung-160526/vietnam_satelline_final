"use strict";
let spatialMap=null,spatialData=null,spatialRequest=0,spatialInitialized=false;
function invalidateSpatial(){
  ++spatialRequest;spatialData=null;
  if(spatialMap){spatialMap.remove();spatialMap=null;}
  $('spatial-results').innerHTML='';$('spatial-legend').innerHTML='';
}
function initSpatial(){
  if(spatialInitialized)return;
  for(const id of ['spatial-start','spatial-end'])
    $(id).innerHTML=Array.from({length:13},(_,i)=>2013+i).map(y=>`<option>${y}</option>`).join('');
  $('spatial-start').value='2020';$('spatial-end').value='2024';
  $('spatial-load').onclick=refreshSpatial;
  $('spatial-mode').onchange=()=>refreshSpatial();
  addEventListener('resize',()=>spatialMap?.resize());spatialInitialized=true;
}
function spatialLink(kind,label,code=''){
  const p=new URLSearchParams({kind,run_id:spatialData.run_id,expected_snapshot:spatialData.snapshot_id,
    year_start:spatialData.year_start,year_end:spatialData.year_end});
  if(code)p.set('province_code',code);
  return `<a class="asset-link" href="/api/spatial/file?${p}">${label}</a>`;
}
async function refreshSpatial(){
  initSpatial();const request=++spatialRequest;
  if(spatialMap){spatialMap.remove();spatialMap=null;}
  spatialData=null;$('spatial-legend').innerHTML='';
  const first=Number($('spatial-start').value),last=Number($('spatial-end').value),code=demoSelection.code;
  const name=danhSachTinh.find(p=>p.province_code===code)?.province_name || 'Toàn quốc';
  $('context-summary').textContent=`${name} · P1 ${first} → ${last} · theo năm`;
  $('spatial-results').innerHTML='<p>Đang đọc phân tích không gian…</p>';
  if(first>=last){$('spatial-results').innerHTML='<p class="canh">Năm đầu phải nhỏ hơn năm cuối.</p>';return;}
  try{
    const data=await layJSON(`/api/spatial?year_start=${first}&year_end=${last}`);
    if(request!==spatialRequest)return;
    checkDemoSnapshot(data);
    if(data.status!=='ready'){
      $('spatial-results').innerHTML=`<p class="canh">${thoat(data.message)}</p>`
        + `<p>Cặp năm đã tính: ${thoat((data.available_pairs || []).map(p=>p.join('–')).join(', ') || 'chưa có')}.</p>`;
      return;
    }
    spatialData=data;
    const selected=data.changes.find(r=>r.province_code===code);
    const td=(v,d=3)=>dinhDang(v,d) ?? '—';
    $('spatial-results').innerHTML=`<h2>Global Moran’s I · mật độ ánh sáng cấp tỉnh</h2>`
      + `<p class="nho">Snapshot ${thoat(data.snapshot_id.slice(0,12))} · P1 v${data.version} · ${first}–${last}. Moran luôn dùng phạm vi toàn bộ tỉnh đủ điều kiện.</p>`
      + `<p>Tiếp giáp Queen, dung sai ${data.tolerance_m} m; chuẩn hóa hàng sau loại thiếu/cô lập. ${data.permutations.toLocaleString('vi-VN')} hoán vị; seed từng năm = ${data.seed} + năm. Kiểm định hai phía quanh E[I].</p>`
      + '<div class="cuon"><table><thead><tr><th>Năm</th><th>I</th><th>E[I]</th><th>p hoán vị</th><th>Số tỉnh</th><th>Trạng thái</th></tr></thead><tbody>'
      + data.moran.map(r=>`<tr><td>${r.year}</td><td>${td(r.moran_i)}</td><td>${td(r.expected_i)}</td><td>${td(r.p_value,4)}</td><td>${r.n}/${r.total_provinces}</td><td>${thoat(({ready:'Đủ tỉnh',partial:'Mẫu thiếu tỉnh',zero_variance:'Biến không có phương sai',insufficient:'Không đủ mẫu'})[r.status] || r.status)}</td></tr>`).join('')
      + '</tbody></table></div><details><summary>Tỉnh tham gia và lý do loại</summary>'
      + data.moran.map(r=>`<p>${r.year}: tham gia ${r.included.map(c=>thoat(danhSachTinh.find(p=>p.province_code===c)?.province_name || c)).join(', ')}.</p><p>Loại: ${thoat(Object.entries(r.exclusion_details).map(([c,reason])=>`${c}: ${reason}`).join('; ') || 'không có')}.</p>`).join('')+'</details>'
      + `<p class="canh">I dương thể hiện các giá trị tương tự có xu hướng gần nhau, I âm thể hiện các giá trị khác nhau có xu hướng gần nhau. Đọc cùng p và cấu trúc trọng số; không kết luận lan tỏa kinh tế hay nhân quả. p chưa hiệu chỉnh khi kiểm định nhiều năm.</p>`
      + spatialLink('moran','CSV Moran')+spatialLink('moran_values','CSV giá trị/mẫu')+spatialLink('neighbors','CSV láng giềng/trọng số')
      + `<h2>Thay đổi vùng sáng · ${first} → ${last}</h2><p>Cùng ngưỡng cố định; lưới năm cuối, nearest; chỉ so sánh vùng có dữ liệu ở cả hai năm. “Sáng” là bức xạ ≥ 1,5 nW/cm²/sr.</p>`
      + `<p>Đã tính ${data.complete_pairs}/${data.expected_provinces} cặp tỉnh. ${code ? 'Bản đồ chi tiết: '+thoat(selected?.province_name || code) : 'Toàn quốc: màu biểu thị thay đổi ròng diện tích sáng / diện tích tỉnh (%). Chọn tỉnh để xem raster chi tiết.'}</p>`
      + (selected?.status==='ready' ? `<div class="fit-grid"><article class="fit-card">Mới sáng<strong>${td(selected.lit_gain_km2,2)} km²</strong></article><article class="fit-card">Mất sáng<strong>${td(selected.lit_loss_km2,2)} km²</strong></article><article class="fit-card">Thay đổi ròng<strong>${td(selected.lit_net_km2,2)} km²</strong></article></div>`
        + `<p>Miền chung ${td(selected.common_area_km2,2)} km² (${td(selected.common_area_pct,2)}% tỉnh). Chỉ năm đầu: ${td(selected.start_only_area_km2,2)} km²; chỉ năm cuối: ${td(selected.end_only_area_km2,2)} km²; thiếu cả hai: ${td(selected.neither_area_km2,2)} km²; ngoài lưới đích: ${td(selected.outside_target_grid_area_km2,2)} km².</p>`
        + `<p>Trọng tâm ánh sáng trên miền chung: ${td(selected.centroid_shift_km,2)} km, hướng ${thoat(selected.direction || 'chưa xác định')}${selected.centroid_bearing_deg!=null ? ' ('+td(selected.centroid_bearing_deg,1)+'° từ Bắc)' : ''}. Trọng số bức xạ ≥ 0,5 × diện tích giao pixel; vị trí xấp xỉ theo tâm ô, không phải dịch chuyển của hoạt động kinh tế đã được chứng minh.</p>`
        + '<div class="cuon"><table><thead><tr><th>Thay đổi</th><th>Diện tích (km²)</th></tr></thead><tbody>'
        + data.change_names.map((name,i)=>`<tr><td>${thoat(name)}</td><td>${td(selected.change_areas_km2[i],2)}</td></tr>`).join('')+'</tbody></table></div>'
        + spatialLink('change','GeoTIFF chuyển vùng/lớp',code)+spatialLink('delta','GeoTIFF chênh lệch bức xạ',code)
        : code ? '<p class="canh">Chưa có miền quan sát chung hoặc cặp VIIRS hợp lệ cho tỉnh này.</p>' : '')
      + spatialLink('changes','CSV thay đổi/trọng tâm')+spatialLink('transitions','CSV ma trận 5×5')+spatialLink('province_changes','GeoJSON cấp tỉnh')
      + data.warnings.map(w=>`<p class="nho">${thoat(w)}</p>`).join('');
    if(typeof maplibregl==='undefined')return;
    const p=new URLSearchParams({kind:'province_changes',run_id:data.run_id,expected_snapshot:data.snapshot_id,year_start:first,year_end:last});
    const geojson=await layJSON('/api/spatial/file?'+p);
    if(request!==spatialRequest)return;
    spatialMap=new maplibregl.Map({container:'spatial-map',style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#080d18'}}]},center:[106,16],zoom:4});
    const map=spatialMap;map.addControl(new maplibregl.NavigationControl());
    map.on('load',()=>{
      if(request!==spatialRequest || map!==spatialMap)return;
      map.addSource('changes',{type:'geojson',data:geojson});
      const target=code ? geojson.features.find(f=>f.properties.province_code===code) : null;
      const filter=code ? ['==',['get','province_code'],code] : ['literal',true];
      map.addLayer({id:'change-fill',type:'fill',source:'changes',filter,paint:{'fill-color':['case',['==',['get','status'],'ready'],['interpolate',['linear'],['coalesce',['get','lit_net_pct'],0],-10,'#fa7469',0,'#26354a',10,'#52cf93'],'#66566b'],'fill-opacity':0.75}});
      if(code && selected?.status==='ready' && data.tiles){
        const kind=$('spatial-mode').value,record=selected.exports[kind];
        const color=JSON.stringify(Object.fromEntries(data.change_colors.map((c,i)=>[i,[parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16),255]])));
        const suffix=kind==='change' ? '&nodata=255&resampling=nearest&colormap='+encodeURIComponent(color) : '&nodata=-9999&rescale=-10,10&colormap_name=rdylgn&resampling=nearest';
        map.addSource('change-raster',{type:'raster',tileSize:256,tiles:[data.tiles+encodeURIComponent(record.path)+suffix]});
        map.addLayer({id:'change-raster',type:'raster',source:'change-raster',paint:{'raster-resampling':'nearest'}});
        map.setPaintProperty('change-fill','fill-opacity',0);
        $('spatial-legend').innerHTML=kind==='change' ? data.change_names.map((name,i)=>`<span class="spatial-key"><i style="background:${data.change_colors[i]}"></i>${thoat(name)}</span>`).join('')
          : 'Chênh lệch bức xạ: đỏ giảm → vàng 0 → xanh tăng; thang hiển thị −10 đến +10 nW/cm²/sr, không giới hạn giá trị dữ liệu.';
      }else $('spatial-legend').textContent='Thay đổi ròng diện tích sáng / diện tích tỉnh (%): đỏ giảm, xanh tăng; thang màu −10 đến +10%. Xám tím: thiếu cặp/miền quan sát chung. '+(code&&!data.tiles ? 'Chưa có dịch vụ ô bản đồ; vẫn tải được GeoTIFF.' : '');
      map.addLayer({id:'change-outline',type:'line',source:'changes',filter,paint:{'line-color':'#b4c5df','line-width':1}});
      if(target){map.fitBounds(bienDo(target),{padding:40,duration:0});}
      else if(geojson.features.length){map.fitBounds(geojson.features.map(bienDo).reduce((b,x)=>[[Math.min(b[0][0],x[0][0]),Math.min(b[0][1],x[0][1])],[Math.max(b[1][0],x[1][0]),Math.max(b[1][1],x[1][1])]]),{padding:30,duration:0});}
      if(selected?.centroid_start && selected?.centroid_end){
        const a=selected.centroid_start,b=selected.centroid_end;
        const coords=[[a.longitude,a.latitude],[b.longitude,b.latitude]];
        map.addSource('shift',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:coords}}});
        map.addLayer({id:'shift',type:'line',source:'shift',paint:{'line-color':'#ffffff','line-width':3}});
        coords.forEach((point,i)=>new maplibregl.Marker({color:i ? '#52cf93':'#fa7469'}).setLngLat(point).setPopup(new maplibregl.Popup().setText('Trọng tâm '+(i?last:first))).addTo(map));
      }
      map.on('click','change-fill',e=>{const props=e.features[0].properties;new maplibregl.Popup().setLngLat(e.lngLat).setText(`${props.province_name}: ${td(props.lit_net_km2,2)} km² thay đổi ròng`).addTo(map);});
    });
  }catch(error){if(request===spatialRequest)$('spatial-results').innerHTML=`<p class="canh">Không đọc được P1: ${thoat(error.message)}</p>`;}
}
