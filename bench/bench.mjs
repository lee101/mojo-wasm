import { loadMojo } from "../js/mojowasm.js";
import { readFile } from "node:fs/promises";
const url = new URL("../build/kernels.wasm", import.meta.url);
const m = await loadMojo(new Uint8Array(await readFile(url)));
const time = (f, reps) => { const t = performance.now(); for (let i=0;i<reps;i++) f(); return (performance.now()-t)/reps; };

const n = 1<<20, reps = 50;
const a = m.allocF64(n), b = m.allocF64(n);
const ja = new Float64Array(n), jb = new Float64Array(n);
for (let i=0;i<n;i++){ ja[i]=i*0.5; jb[i]=i%7; }
a.set(ja); b.set(jb);
const jsSum = () => { let s=0; for (let i=0;i<n;i++) s+=ja[i]; return s; };
const jsDot = () => { let s=0; for (let i=0;i<n;i++) s+=ja[i]*jb[i]; return s; };
console.log(`sum  2^20  wasm ${time(()=>m.exports.sum(a.ptr,n),reps).toFixed(3)}ms   js ${time(jsSum,reps).toFixed(3)}ms`);
console.log(`dot  2^20  wasm ${time(()=>m.exports.dot(a.ptr,b.ptr,n),reps).toFixed(3)}ms   js ${time(jsDot,reps).toFixed(3)}ms`);

const S=128;
const A=m.allocF64(S*S).set(Float64Array.from({length:S*S},(_,i)=>(i%13)*0.25));
const B=m.allocF64(S*S).set(Float64Array.from({length:S*S},(_,i)=>(i%5)*0.5));
const C=m.allocF64(S*S);
const jA=Float64Array.from({length:S*S},(_,i)=>(i%13)*0.25), jB=Float64Array.from({length:S*S},(_,i)=>(i%5)*0.5), jC=new Float64Array(S*S);
const jsMM=()=>{ jC.fill(0); for(let i=0;i<S;i++) for(let k=0;k<S;k++){const av=jA[i*S+k]; for(let j=0;j<S;j++) jC[i*S+j]+=av*jB[k*S+j];} };
console.log(`matmul 128 wasm ${time(()=>m.exports.matmul(A.ptr,B.ptr,C.ptr,S,S,S),20).toFixed(3)}ms   js ${time(jsMM,20).toFixed(3)}ms`);

const mb = await loadMojo(new Uint8Array(await readFile(new URL("../build/mandelbrot.wasm", import.meta.url))));
const w=800,h=600,px=mb.allocU8(w*h);
const jsMandel=()=>{const g=new Uint8Array(w*h);const it=300,scale=3.0/w;
  for(let y=0;y<h;y++){const im=(y-h/2)*scale;
    for(let x=0;x<w;x++){const re=-0.6+(x-w/2)*scale;let zr=0,zi=0,i=0;
      while(i<it){const zr2=zr*zr,zi2=zi*zi;if(zr2+zi2>4)break;zi=2*zr*zi+im;zr=zr2-zi2+re;i++;}
      g[y*w+x]=(i*255/it)|0;}}};
console.log(`mandelbrot 800x600@300 wasm ${time(()=>mb.exports.mandelbrot(px.ptr,w,h,300,-0.6,0,3.0/w),5).toFixed(1)}ms   js ${time(jsMandel,5).toFixed(1)}ms`);
