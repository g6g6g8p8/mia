// Standard SHA-256 and ZIP checksums, computed a chunk at a time. No file is
// decoded into a base64 string or loaded completely into browser memory.
const SHA_CONSTANTS = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
]);
const rotate=(n,b)=>(n>>>b)|(n<<(32-b));
class SHA256 {
  constructor(){this.state=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);this.buffer=new Uint8Array(64);this.used=0;this.length=0;this.words=new Uint32Array(64);}
  block(bytes,offset=0){
    const w=this.words;
    for(let i=0;i<16;i++){const p=offset+i*4;w[i]=(bytes[p]<<24)|(bytes[p+1]<<16)|(bytes[p+2]<<8)|bytes[p+3];}
    for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2];w[i]=(w[i-16]+(rotate(a,7)^rotate(a,18)^(a>>>3))+w[i-7]+(rotate(b,17)^rotate(b,19)^(b>>>10)))>>>0;}
    let [a,b,c,d,e,f,g,h]=this.state;
    for(let i=0;i<64;i++){
      const first=(h+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+SHA_CONSTANTS[i]+w[i])>>>0;
      const second=((rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
      h=g;g=f;f=e;e=(d+first)>>>0;d=c;c=b;b=a;a=(first+second)>>>0;
    }
    [a,b,c,d,e,f,g,h].forEach((v,i)=>{this.state[i]=(this.state[i]+v)>>>0;});
  }
  update(bytes){
    this.length+=bytes.length;let offset=0;
    if(this.used){const n=Math.min(64-this.used,bytes.length);this.buffer.set(bytes.subarray(0,n),this.used);this.used+=n;offset=n;if(this.used===64){this.block(this.buffer);this.used=0;}}
    for(;offset+64<=bytes.length;offset+=64)this.block(bytes,offset);
    if(offset<bytes.length){this.buffer.set(bytes.subarray(offset),0);this.used=bytes.length-offset;}
  }
  digest(){
    const length=this.length;this.buffer[this.used++]=128;
    if(this.used>56){this.buffer.fill(0,this.used);this.block(this.buffer);this.used=0;}
    this.buffer.fill(0,this.used,56);
    const view=new DataView(this.buffer.buffer);view.setUint32(56,Math.floor(length/0x20000000));view.setUint32(60,(length*8)>>>0);this.block(this.buffer);
    return Array.from(this.state,n=>n.toString(16).padStart(8,'0')).join('');
  }
}
export async function fileChecksum(file,onProgress=()=>{},signal){
  const hash=new SHA256();
  for(let offset=0;offset<file.size;offset+=1024*1024){
    if(signal?.aborted)throw new DOMException('Preparação interrompida','AbortError');
    hash.update(new Uint8Array(await file.slice(offset,offset+1024*1024).arrayBuffer()));
    onProgress(Math.min(file.size,offset+1024*1024),file.size);
    await new Promise(resolve=>setTimeout(resolve,0));
  }
  return hash.digest();
}
const CRC_TABLE=new Uint32Array(256);
for(let i=0;i<256;i++){let n=i;for(let bit=0;bit<8;bit++)n=(n&1)?0xedb88320^(n>>>1):n>>>1;CRC_TABLE[i]=n>>>0;}
async function crc(file,signal){
  let value=0xffffffff;
  for(let offset=0;offset<file.size;offset+=1024*1024){
    if(signal?.aborted)throw new DOMException('Preparação interrompida','AbortError');
    const bytes=new Uint8Array(await file.slice(offset,offset+1024*1024).arrayBuffer());
    for(const byte of bytes)value=CRC_TABLE[(value^byte)&255]^(value>>>8);
    await new Promise(resolve=>setTimeout(resolve,0));
  }
  return (value^0xffffffff)>>>0;
}
export function folderInventory(files){
  const accepted=[],ignored=[];
  for(const file of files){
    const path=file.webkitRelativePath || file.name;
    if(path.split('/').some(part=>part.startsWith('.') || ['node_modules','__MACOSX'].includes(part)) || !/\.(md|markdown|txt|json)$/i.test(path)){ignored.push(path);continue;}
    accepted.push({file,path});
  }
  return {accepted,ignored,size:accepted.reduce((sum,item)=>sum+item.file.size,0)};
}
export async function folderArchive(inventory,onProgress=()=>{},signal){
  const parts=[],central=[];let offset=0;
  const encoder=new TextEncoder();
  for(let i=0;i<inventory.accepted.length;i++){
    const {file,path}=inventory.accepted[i],name=encoder.encode(path);
    if(name.length>65535 || file.size>0xffffffff)throw new Error('Nome ou arquivo ultrapassa o formato ZIP suportado');
    const checksum=await crc(file,signal);
    const local=new Uint8Array(30+name.length),view=new DataView(local.buffer);
    view.setUint32(0,0x04034b50,true);view.setUint16(4,20,true);view.setUint16(6,0x0800,true);
    const date=new Date(file.lastModified || Date.now()),year=Math.max(1980,Math.min(2107,date.getUTCFullYear()));
    const day=((year-1980)<<9)|((date.getUTCMonth()+1)<<5)|date.getUTCDate();
    const time=(date.getUTCHours()<<11)|(date.getUTCMinutes()<<5)|Math.floor(date.getUTCSeconds()/2);
    view.setUint16(10,time,true);view.setUint16(12,day,true);view.setUint32(14,checksum,true);
    view.setUint32(18,file.size,true);view.setUint32(22,file.size,true);view.setUint16(26,name.length,true);local.set(name,30);
    const directory=new Uint8Array(46+name.length),entry=new DataView(directory.buffer);
    entry.setUint32(0,0x02014b50,true);entry.setUint16(4,20,true);entry.setUint16(6,20,true);entry.setUint16(8,0x0800,true);
    entry.setUint16(12,time,true);entry.setUint16(14,day,true);entry.setUint32(16,checksum,true);entry.setUint32(20,file.size,true);entry.setUint32(24,file.size,true);entry.setUint16(28,name.length,true);entry.setUint32(42,offset,true);directory.set(name,46);
    parts.push(local,file);central.push(directory);offset+=local.length+file.size;onProgress(i+1,inventory.accepted.length);
  }
  if(inventory.accepted.length>65535 || offset>0xffffffff)throw new Error('Pasta ultrapassa o formato ZIP suportado');
  const end=new Uint8Array(22),view=new DataView(end.buffer),centralSize=central.reduce((sum,part)=>sum+part.length,0);
  view.setUint32(0,0x06054b50,true);view.setUint16(8,central.length,true);view.setUint16(10,central.length,true);view.setUint32(12,centralSize,true);view.setUint32(16,offset,true);
  return new File([...parts,...central,end],(inventory.accepted[0]?.path.split('/')[0] || 'pasta')+'.zip',{type:'application/zip'});
}
