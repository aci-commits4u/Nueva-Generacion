/**
 * Errors from the AI path are deliberately safe for the browser. The server
 * may include a public error envelope alongside its plain detail message;
 * preserve that envelope so the UI can distinguish quota, provider, and
 * interpretation failures without exposing a provider payload.
 */
export class ApiError extends Error {
 constructor(path,status,data={},cause=null){
  const detail=data?.detail;
  const publicError=data?.error&&typeof data.error==='object'?data.error:{};
  const message=typeof detail==='string'?detail:detail?.message||publicError.message||'The request could not be completed.';
  super(message,{cause});
  this.name='ApiError';
  this.path=path;
  this.status=status;
  this.code=publicError.code||detail?.code||null;
  this.retryable=publicError.retryable===true;
  this.retryAfterSeconds=publicError.retry_after_seconds??detail?.retry_after_seconds??null;
  this.requestId=publicError.request_id||detail?.request_id||null;
  this.publicError=publicError;
 }
}

export function errorFromUnknown(error,path=''){
 if(error instanceof ApiError)return error;
 const message=error?.message||'The connection was interrupted.';
 return new ApiError(path,0,{detail:message},error);
}

export async function api(path,body){
 let response;
 try{
  response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin'});
 }catch(error){throw errorFromUnknown(error,path);}
 let data={};
 try{
  const text=await response.text();
  data=text?JSON.parse(text):{};
 }catch(error){
  if(!response.ok)throw new ApiError(path,response.status,{detail:'The service returned an unreadable response.'},error);
  throw new ApiError(path,response.status,{detail:'The service returned an unreadable response.'},error);
 }
 if(!response.ok)throw new ApiError(path,response.status,data);
 return data;
}
