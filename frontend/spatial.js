"use strict";
let spatialMap=null,spatialRequest=0,spatialInitialized=false;
function invalidateSpatial(){++spatialRequest;$('spatial-results').innerHTML='';}
function initSpatial(){
 if(spatialInitialized)return;
 for(const id of ['spatial-start','spatial-end'])$(id).innerHTML=Array.from({length:13},(_,i)=>2013+i).map(y=>`<option>${y}</option>`).join('');
 $('spatial-start').value='2020';$('spatial-end').value='2024';$('spatial-load').onclick=refreshSpatial;spatialInitialized=true;
}
async function refreshSpatial(){
 initSpatial();const request=++spatialRequest,first=Number($('spatial-start').value),last=Number($('spatial-end').value);
 $('context-summary').textContent=`Moran · ${first}–${last}`;
 if(first>=last){$('spatial-results').textContent='Năm đầu phải nhỏ hơn năm cuối.';return;}
 try{
  const data=await layJSON(`/api/spatial?year_start=${first}&year_end=${last}`);if(request!==spatialRequest)return;
  if(data.status!=='ready'){$('spatial-results').textContent=data.message;return;}
  const p=new URLSearchParams({year_start:first,year_end:last,kind:'moran',run_id:data.run_id,expected_snapshot:data.snapshot_id});
  $('spatial-results').innerHTML='<h2>Moran’s I cấp tỉnh</h2><p>Đo tự tương quan không gian của mật độ ánh sáng; không chứng minh lan tỏa kinh tế hay quan hệ nhân quả.</p><table><thead><tr><th>year</th><th>moran_i</th></tr></thead><tbody>'+data.moran.map(r=>`<tr><td>${r.year}</td><td>${dinhDang(r.moran_i,4)??'—'}</td></tr>`).join('')+'</tbody></table>'+`<a class="asset-link" href="/api/spatial/file?${p}">Tải CSV Moran</a>`;
 }catch(error){if(request===spatialRequest)$('spatial-results').textContent=error.message;}
}
