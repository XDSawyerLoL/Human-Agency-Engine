import assert from "node:assert/strict";
import { createServer } from "node:http";

const [{createMySqlRelayPersistence},{createEmbeddedRelay}]=await Promise.all([
  import("../vendor/quanticmail-relay/standalone-relay/mysql-storage.ts"),
  import("../vendor/quanticmail-relay/standalone-relay/embedded.ts"),
]);

class FakeMySql{
  rows=new Map();
  async execute(sql,params=[]){
    const q=sql.replace(/\s+/g," ").trim().toLowerCase();
    if(q.startsWith("create table"))return [[],{affectedRows:0}];
    if(q.startsWith("select value, revision")){
      const row=this.rows.get(String(params[0]??""));
      return [row?[{value:JSON.stringify(row.value),revision:row.revision}]:[],{}];
    }
    if(q.startsWith("select value")){
      const row=this.rows.get(String(params[0]??""));
      return [row?[{value:JSON.stringify(row.value)}]:[],{}];
    }
    if(q.startsWith("insert ignore")){
      const key=String(params[0]??"");
      if(this.rows.has(key))return [[],{affectedRows:0}];
      this.rows.set(key,{value:JSON.parse(String(params[1]??"null")),revision:Number(params[2]??0)});
      return [[],{affectedRows:1}];
    }
    if(q.startsWith("insert into")&&q.includes("on duplicate key update")){
      const key=String(params[0]??"");
      const current=this.rows.get(key);
      this.rows.set(key,{value:JSON.parse(String(params[1]??"null")),revision:current?.revision??0});
      return [[],{affectedRows:1}];
    }
    if(q.startsWith("update quantic_relay_kv")){
      const key=String(params[1]??"");
      const expected=Number(params[2]);
      const row=this.rows.get(key);
      if(!row||row.revision!==expected)return [[],{affectedRows:0}];
      row.value=JSON.parse(String(params[0]??"null"));
      row.revision+=1;
      return [[],{affectedRows:1}];
    }
    throw new Error(`Unexpected SQL ${q}`);
  }
}

const persistence=createMySqlRelayPersistence(new FakeMySql(),{
  identitySecret:"hostinger-vendored-relay-ci-secret-long-enough-2026",
});
const relay=await createEmbeddedRelay({
  persistence,
  publicEndpoint:"https://mediumorchid-badger-314305.hostingersite.com",
  bootstrapEndpoints:[],
});

const server=createServer((req,res)=>{
  void relay.handle(req,res).then(handled=>{
    if(!handled&&!res.writableEnded){res.statusCode=404;res.end("not-found");}
  });
});
await new Promise((resolve,reject)=>{
  server.once("error",reject);
  server.listen(0,"127.0.0.1",resolve);
});
const address=server.address();
assert.ok(address&&typeof address!=="string");
const response=await fetch(`http://127.0.0.1:${address.port}/api/quantic/health`);
assert.equal(response.status,200);
const payload=await response.json();
assert.equal(payload.ok,true);
assert.equal(payload.protocol,"quantic-relay/1");
assert.match(payload.relayId,/^[0-9a-f]{64}$/);

await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
await relay.close();
console.log(JSON.stringify({ok:true,contract:"vendored-embedded-relay",relayId:payload.relayId}));
