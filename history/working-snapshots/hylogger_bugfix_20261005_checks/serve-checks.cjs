const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const allowed = new Set(['media-regression.html','holemap-regression.html']);
http.createServer((req,res)=>{
 const file = new URL(req.url,'http://localhost').pathname.slice(1);
 if(!allowed.has(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type','text/html; charset=utf-8');
 res.end(fs.readFileSync(path.join(__dirname,file)));
}).listen(3107,'127.0.0.1',()=>console.log('Regression pages on http://127.0.0.1:3107'));
