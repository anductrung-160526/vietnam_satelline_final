"use strict";
let wideData=null,widePage=0,wideRequest=0,wideQuery=null;
const WIDE_PAGE_SIZE=100;
/* app.js hỏi trước khi nạp: bảng chi tiết chỉ gọi API khi người dùng mở tới nó. */
function wideTableNeedsLoad(){return wideData===null;}
function invalidateWideTable(){++wideRequest;wideData=null;wideQuery=null;renderWideTable();}
function wideParams(){
  const params=thamSoBang();params.delete('ham');
  return params;
}
async function loadWideTable(){
  const request=++wideRequest;
  if(!chon.tinh.size || !chon.moc.size || !chon.chiSo.size){wideData=null;renderWideTable();return;}
  try{
    const params=wideParams();
    const data=await layJSON('/api/demo/data?'+params);
    if(request!==wideRequest)return;
    checkDemoSnapshot(data);wideData=data;wideQuery=params;widePage=0;renderWideTable();
  }catch(error){
    if(request!==wideRequest)return;
    wideData=null;renderWideTable();$('data-table-summary').textContent='Không đọc được bảng: '+error.message;
  }
}
function renderWideTable(){
  const table=$('data-table');
  if(!wideData){table.innerHTML='';$('data-table-summary').textContent='Chọn tỉnh, chỉ số và mốc năm/tháng để xem bảng.';$('data-page').textContent='';return;}
  const pages=Math.max(1,Math.ceil(wideData.rows.length/WIDE_PAGE_SIZE));widePage=Math.max(0,Math.min(widePage,pages-1));
  const start=widePage*WIDE_PAGE_SIZE,rows=wideData.rows.slice(start,start+WIDE_PAGE_SIZE);
  const groups=[['identity','Định danh'],['raw','Raw — dữ liệu đầu vào'],['processed','Processed — kết quả tính toán']];
  const groupHeader=groups.map(([key,label])=>{
    const count=wideData.columns.filter(c=>c.group===key).length;
    return count ? `<th colspan="${count}" class="group-${key}">${label}</th>` : '';
  }).join('');
  const cell=(row,column)=>{
    const value=row[column.field];
    if(value==null)return '<td class="rong" title="Thiếu số liệu hoặc không áp dụng ở mốc này">—</td>';
    if(column.field==='avg_rad' || column.field==='cf_cvg'){
      const p=new URLSearchParams({province_code:row.province_code,nam:row.year,thang:row.month,kind:'raw'});
      if(wideData.snapshot_id)p.set('expected_snapshot',wideData.snapshot_id);
      return `<td><a href="/api/demo/image?${p}" title="${thoat(value)}">${column.field} · băng ${column.field==='avg_rad'?1:2}</a></td>`;
    }
    const text=typeof value==='boolean' ? (value?'true':'false') : column.numeric && !['year','month','price_base_year'].includes(column.field) ? dinhDang(value,4) : value;
    return `<td title="${thoat(value)}">${thoat(text)}</td>`;
  };
  table.innerHTML=`<thead><tr>${groupHeader}</tr><tr>`
    +wideData.columns.map(c=>`<th class="group-${c.group}" title="${thoat(c.name)}"><code>${thoat(c.field)}</code><small>${thoat(c.name)}</small></th>`).join('')
    +'</tr></thead><tbody>'+rows.map(row=>'<tr>'+wideData.columns.map(c=>cell(row,c)).join('')+'</tr>').join('')+'</tbody>';
  $('data-table-summary').textContent=`${wideData.rows.length.toLocaleString('vi-VN')} dòng · ${wideData.columns.length} cột · định danh → Raw → Processed. Tháng 0 là dòng năm. GRDP ở dòng tháng để trống.`;

  $('data-page').textContent=`Trang ${widePage+1}/${pages} · dòng ${rows.length ? start+1:0}–${start+rows.length}`;
  $('data-prev').disabled=widePage===0;$('data-next').disabled=widePage===pages-1;
  $('data-prev').onclick=()=>{widePage--;renderWideTable();};$('data-next').onclick=()=>{widePage++;renderWideTable();};
}
function downloadWideTable(){
  if(!wideData || demoSnapshotChanged)return;
  const params=new URLSearchParams(wideQuery);if(wideData.snapshot_id)params.set('expected_snapshot',wideData.snapshot_id);
  window.location='/api/demo/data.csv?'+params;
}
