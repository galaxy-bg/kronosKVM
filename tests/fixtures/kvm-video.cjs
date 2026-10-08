const assert=require('node:assert/strict');
const {JPEGFrames,CompleteVideoStream}=require(process.cwd()+'/frontend/src/kvm-video.js');
const jpeg=Uint8Array.from([255,216,1,2,3,255,217]);
const wire=Buffer.concat([Buffer.from('--ffmpeg\r\nContent-Type: image/jpeg\r\n\r\n'),jpeg,Buffer.from('\r\n--ffmpeg\r\n'),jpeg]);
for(let boundary=0;boundary<=wire.length;boundary++){
 const parser=new JPEGFrames();const frames=[...parser.push(wire.subarray(0,boundary)),...parser.push(wire.subarray(boundary))];
 assert.equal(frames.length,2);assert.deepEqual(frames.map(f=>Array.from(f)),[Array.from(jpeg),Array.from(jpeg)]);
}
const parser=new JPEGFrames();const out=[];for(const byte of wire)out.push(...parser.push(Uint8Array.of(byte)));assert.equal(out.length,2);
assert.throws(()=>new JPEGFrames().push(new Uint8Array(8*1024*1024+1)),/limit/);
(async()=>{
 let resolveDecode;
 global.Image=class{decode(){return new Promise(resolve=>{resolveDecode=resolve})}};
 const displayed={src:'last-good',removeAttribute(){this.src=''}};
 const stream=new CompleteVideoStream(displayed);
 let operation=stream.present(jpeg,stream.generation);assert.equal(displayed.src,'last-good');resolveDecode();await operation;assert.match(displayed.src,/^blob:/);
 const saved=displayed.src;
 operation=stream.present(jpeg,stream.generation);stream.stop();resolveDecode();await operation;assert.equal(displayed.src,saved);
 stream.dispose();assert.equal(displayed.src,'');assert.equal(stream.currentURL,null);
 console.log('PASS: every multipart split, single-byte reads, multiple JPEG frames, bounds, decode-before-display and stop-race cleanup');
})().catch(e=>{console.error(e);process.exitCode=1});
