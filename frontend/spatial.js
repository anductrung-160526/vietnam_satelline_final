"use strict";
let spatialRequest=0;
function invalidateSpatial(){++spatialRequest;$('spatial-results').innerHTML='';}
async function refreshSpatial(){
 const request=++spatialRequest,[first,last]=economyRange();
 if(first>last)return;
 $('spatial-results').textContent='Đang đọc Moran’s I…';
 try{
  const data=await layJSON(`/api/spatial?year_start=${first}&year_end=${last}`);if(request!==spatialRequest)return;
  if(data.status!=='ready'){$('spatial-results').textContent=data.message;return;}
  const p=new URLSearchParams({year_start:first,year_end:last,kind:'moran',run_id:data.run_id,expected_snapshot:data.snapshot_id});
  $('spatial-results').innerHTML='<p>Moran’s I của mật độ ánh sáng trên toàn bộ tỉnh đủ điều kiện, theo khoảng năm phân tích ở trên; không tính riêng một tỉnh. Chỉ số mô tả tự tương quan không gian, không chứng minh lan tỏa kinh tế hay nhân quả.</p><table><thead><tr><th>Năm</th><th>moran_i</th></tr></thead><tbody>'+data.moran.map(r=>`<tr><td>${r.year}</td><td>${dinhDang(r.moran_i,4)??'—'}</td></tr>`).join('')+'</tbody></table>'+`<a class="asset-link" href="/api/spatial/file?${p}">Tải CSV Moran</a>`;
 }catch(error){if(request===spatialRequest)$('spatial-results').textContent=error.message;}
}
