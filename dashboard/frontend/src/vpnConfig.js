// Private key material is generated here, never submitted to an API or browser storage.
const encode=bytes=>btoa(String.fromCharCode(...bytes));
function decodeUrl(value){const text=value.replaceAll('-','+').replaceAll('_','/');return Uint8Array.from(atob(text+'='.repeat((4-text.length%4)%4)),c=>c.charCodeAt(0));}
function key(value){if(typeof value!=='string'||! /^[A-Za-z0-9+/]{43}=$/.test(value))throw Error('Invalid VPN key.');const raw=Uint8Array.from(atob(value),c=>c.charCodeAt(0));if(raw.length!==32||raw.every(x=>x===0)||encode(raw)!==value)throw Error('Invalid VPN key.');return value;}
function ip(value){const parts=value.split('.');if(parts.length!==4||parts.some(p=>! /^(0|[1-9][0-9]{0,2})$/.test(p)||Number(p)>255))throw Error('Invalid VPN address.');return parts.reduce((n,p)=>(n*256+Number(p))>>>0,0);}
function network(value){if(typeof value!=='string'||/[\r\n]/.test(value))throw Error('Invalid VPN network.');const parts=value.split('/');if(parts.length!==2||! /^([1-9]|[12][0-9]|3[0-2])$/.test(parts[1]))throw Error('Invalid VPN network.');const bits=Number(parts[1]),address=ip(parts[0]),mask=(0xffffffff<<(32-bits))>>>0;const privateNet=(address>>>24===10&&bits>=8)||(address>>>20===0xac1&&bits>=12)||(address>>>16===0xc0a8&&bits>=16);if(!privateNet)throw Error('Only private VPN networks are supported.');return{address,mask,bits,base:(address&mask)>>>0};}
export async function generateClientIdentity(){
 if(globalThis.isSecureContext===false||!globalThis.crypto?.subtle)throw Error('Open the HTTPS dashboard in a current browser to generate a configuration.');
 let pair;try{pair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);}catch{throw Error('Your browser does not support VPN key generation. Use a current browser.');}
 const jwk=await crypto.subtle.exportKey('jwk',pair.privateKey);
 const publicKey=encode(new Uint8Array(await crypto.subtle.exportKey('raw',pair.publicKey)));
 const privateKey=encode(decodeUrl(jwk.d));key(publicKey);key(privateKey);
 return{id:crypto.randomUUID(),publicKey,privateKey};
}
export function clientConfiguration(identity,registration){
 if(!registration||registration.version!==2||registration.client_id!==identity.id||registration.public_key!==identity.publicKey)throw Error('The VPN response does not match this computer key.');
 key(identity.publicKey);key(identity.privateKey);key(registration.server_public_key);
 const address=network(registration.address);if(address.bits!==32)throw Error('Client VPN address must use /32.');
 const routes=registration.allowed_ips?.split(',').map(s=>s.trim());if(!routes?.length||routes.length>16)throw Error('Invalid VPN routes.');
 const parsed=routes.map(network);if(parsed.some(n=>n.address!==n.base)||!parsed.some(n=>((address.address&n.mask)>>>0)===n.base))throw Error('VPN address is outside the allowed network.');
 const endpoint=registration.endpoint;if(typeof endpoint!=='string'||/[\r\n]/.test(endpoint)||! /^[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}$/.test(endpoint)||Number(endpoint.split(':')[1])<1||Number(endpoint.split(':')[1])>65535)throw Error('Invalid VPN server.');
 if(!Number.isInteger(registration.keepalive)||registration.keepalive<0||registration.keepalive>120)throw Error('Invalid VPN connection setting.');
 return `[Interface]\nPrivateKey = ${identity.privateKey}\nAddress = ${registration.address}\n\n[Peer]\nPublicKey = ${registration.server_public_key}\nEndpoint = ${endpoint}\nAllowedIPs = ${routes.join(', ')}\nPersistentKeepalive = ${registration.keepalive}\n`;
}
