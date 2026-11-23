"use strict";
let spatialRequest=0;
function invalidateSpatial(){++spatialRequest;$('spatial-results').innerHTML='';}
async function refreshSpatial(){
 const request=++spatialRequest,[first,last]=economyRange();
 if(first>last)return;
 $('spatial-results').textContent='Đang đọc Moran’s I…';
 try{
  const data=await layJSON(`/api/spatial?year_start=${first}&year_end=${last}`);if(request!==spatialRequest)return;
  if(data.status!=='ready'){
    const saved=(data.available_pairs || []).map(([a,b])=>a===b?String(a):`${a}–${b}`).join('; ');
    $('spatial-results').textContent=data.message+(saved?' Khoảng năm của các lượt đã lưu: '+saved+'.':'');return;
  }
  const p=new URLSearchParams({year_start:first,year_end:last,kind:'moran',run_id:data.run_id,expected_snapshot:data.snapshot_id});
  const coverage=data.missing_years?.length
    ? `<p class="canh">Khoảng yêu cầu: ${first}–${last}. Hiển thị kết quả đã tính cho ${data.available_years.join(', ')}. Chưa có kết quả cho ${data.missing_years.join(', ')}; không nội suy hoặc thay bằng 0.</p>`:'';
  $('spatial-results').innerHTML='<p>Moran’s I đo tự tương quan không gian của mật độ kinh tế đêm theo ánh sáng (SOL/diện tích tỉnh), trên toàn bộ tỉnh đủ điều kiện của từng năm; không tính riêng một tỉnh và không dùng mã năm lớp sáng làm biến đầu vào. Kết quả được đọc từ lượt phân tích đã kiểm chứng, không tính mới khi đổi bộ lọc. Chỉ số không chứng minh lan tỏa kinh tế hay nhân quả.</p>'+coverage+'<table><thead><tr><th>Năm</th><th>Moran’s I</th></tr></thead><tbody>'+data.moran.map(r=>`<tr><td>${r.year}</td><td>${dinhDang(r.moran_i,4)??'—'}</td></tr>`).join('')+'</tbody></table>'+`<a class="asset-link" href="/api/spatial/file?${p}">Tải CSV Moran</a>`;
 }catch(error){if(request===spatialRequest)$('spatial-results').textContent=error.message;}
}
