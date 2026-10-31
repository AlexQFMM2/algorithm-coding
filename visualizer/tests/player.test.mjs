import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as esbuild from 'esbuild';
import {common} from '../build.mjs';
import {createRequire} from 'node:module';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const temp = await mkdtemp(path.join(os.tmpdir(), 'algorithm-player-'));
const result = await esbuild.build({...common, entryPoints: [new URL('../src/player.js', import.meta.url).pathname],
  write:false, platform:'node', format:'cjs', loader:{'.js':'jsx','.css':'empty','.module.css':'empty'}, logLevel:'silent'});
const file = path.join(temp,'player.cjs');await writeFile(file,result.outputFiles[0].contents);
const {TracePlayer} = createRequire(import.meta.url)(file);
await rm(temp,{recursive:true});
const command=(key,method,...args)=>({key,method,args});
const trace={commands:[
  command('a','Array1DTracer','数组'),command('a','set',[2,1]),
  command('log','LogTracer','解释'),command('log','set','开始'),
  command('root','VerticalLayout',['a','log']),command(null,'setRoot','root'),
  command(null,'delay',1,{kind:'start'}),
  command('a','select',0),command('a','patch',1,2),command('log','set','<b>文本</b>'),
  command(null,'delay',2,{kind:'count',before:0,after:1}),
  command('a','set',[1,2]),command(null,'delay',3,{kind:'complete'})]};
const state=player=>JSON.stringify([player.objects.a.data,player.objects.log.log,player.current]);
test('forward, backward, and direct seek reconstruct the same upstream models',()=>{
 const p=new TracePlayer(trace);const start=state(p);assert.equal(p.nextCount(),1);
 p.seek(1);const middle=state(p);assert.equal(p.objects.a.data[0][0].selected,true);
 p.seek(2);assert.deepEqual(p.objects.a.data[0].map(x=>x.value),[1,2]);
 p.seek(0);assert.equal(state(p),start);p.seek(1);assert.equal(state(p),middle);
 const fresh=new TracePlayer(trace);fresh.seek(1);assert.equal(state(fresh),middle);
 assert.equal(p.seek(-1),false);assert.equal(p.seek(3),false);
});
test('unrecognized commands and incomplete trailing operations fail visibly',()=>{
 assert.throws(()=>new TracePlayer({commands:[...trace.commands,command('a','set',[9])]}),/不完整/);
 assert.throws(()=>new TracePlayer({commands:[command('a','constructor'),command(null,'delay',1)]}),/无法播放/);
});
