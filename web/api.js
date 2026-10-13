export async function api(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin'});
 const data=await response.json();
 if(!response.ok){const detail=data.detail;throw new Error(typeof detail==='string'?detail:detail?.message||'The request could not be completed. Review your inputs.');}
 return data;
}
