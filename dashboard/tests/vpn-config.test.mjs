import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,createPrivateKey,createPublicKey} from 'node:crypto';
import {generateClientIdentity,clientConfiguration} from '../frontend/src/vpnConfig.js';
const server=Buffer.alloc(32,9).toString('base64');
function registration(identity,extra={}){return{version:2,client_id:identity.id,public_key:identity.publicKey,address:'10.77.0.12/32',server_public_key:server,endpoint:'vpn.example.com:51820',allowed_ips:'10.77.0.0/24',keepalive:25,...extra};}
test('browser X25519 raw key matches independent OpenSSL public-key derivation',async()=>{
 const value=await generateClientIdentity();
 // RFC 8410 PKCS#8 contains only the raw private scalar, no supplied public key.
 const der=Buffer.concat([Buffer.from('302e020100300506032b656e04220420','hex'),Buffer.from(value.privateKey,'base64')]);
 const independent=createPublicKey(createPrivateKey({key:der,format:'der',type:'pkcs8'})).export({format:'jwk'});
 assert.equal(Buffer.from(independent.x,'base64url').toString('base64'),value.publicKey);
 const conf=clientConfiguration(value,registration(value));
 assert(conf.includes('PrivateKey = '+value.privateKey));assert(conf.includes('Address = 10.77.0.12/32'));
 assert(!conf.includes('0.0.0.0/0'));assert(!conf.includes('DNS ='));
});
test('configuration rejects key mismatch, route injection and arbitrary profile directives',async()=>{
 const value=await generateClientIdentity();
 for(const extra of [{public_key:server},{client_id:'wrong'},{endpoint:'vpn.test:51820\nPostUp = command'},{allowed_ips:'0.0.0.0/0'},{allowed_ips:'10.77.0.0/24\nDNS = 8.8.8.8'},{address:'10.77.0.12/24'},{allowed_ips:'192.168.1.0/24'},{keepalive:'25\ncommand'}]){
  assert.throws(()=>clientConfiguration(value,registration(value,extra)));
 }
});
