// End-to-end acceptance: only synthetic fixtures and temporary workspaces.
const {chromium}=require('playwright');const fs=require('node:fs/promises');const os=require('node:os');const path=require('node:path');
const {spawn}=require('node:child_process');const assert=require('node:assert/strict');
const repo=path.resolve(__dirname,'../..');
const screenshots=process.env.VIZ_SCREENSHOTS;
async function screenshot(page,name){if(screenshots){await fs.mkdir(screenshots,{recursive:true});await page.screenshot({path:path.join(screenshots,name)});}}
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'algorithm-viz-browser-'));
 const problem=path.join(root,'题库/演示测试');await fs.mkdir(path.join(problem,'tests'),{recursive:true});
 const source=await fs.readFile(path.join(repo,'visualizer/examples/inversions.cpp'),'utf8');
 const config={title:'逆序对的数量',samples:[{input:'4\n4 1 3 2\n',output:'4\n'}],visualization:{source:'visualize.cpp',title:'逆序对：一次数清左边剩余的配对',input_hint:'第一行 n（1～20），第二行恰好 n 个整数（1～1000000000）。'}};
 for(const [file,text] of Object.entries({'题目.md':'# 测试说明\n\n'+('测试阅读位置。\n\n'.repeat(50)),'practice.json':JSON.stringify(config),'visualize.cpp':source,'main.cpp':'#include <iostream>\nint main(){\n  int n;\n  std::cin>>n;\n  std::cout<<n;\n}\n','tests/001.in':'1\n','tests/001.out':'1\n'}))await fs.writeFile(path.join(problem,file),text);
 const server=spawn('python3',['app.py','--root',root,'--no-browser','--port','0'],{cwd:repo});let browser;
 try{
  const base=await new Promise((resolve,reject)=>{
   let output='';
   const timer=setTimeout(()=>reject(new Error('Server did not start: '+output)),15000);
   server.stderr.on('data',d=>{output+=d;});
   server.once('error',e=>{clearTimeout(timer);reject(e);});
   server.once('exit',code=>{clearTimeout(timer);reject(new Error('Server exited: '+code+' '+output));});
   server.stdout.on('data',d=>{output+=d;const m=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});
  });
  browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.route('**/*',r=>{if(new URL(r.request().url()).origin!==base){external.push(r.request().url());return r.abort();}return r.continue();});
  await page.goto(base);await page.waitForFunction(()=>!document.querySelector('#visualize').disabled);
  await page.evaluate(()=>{ace.edit('code').navigateFileEnd();ace.edit('code').insert('\n// retained draft\n');ace.edit('code').moveCursorTo(3,2);document.querySelector('#document-content').scrollTop=130;});
  const before=await page.evaluate(()=>({code:ace.edit('code').getValue(),cursor:ace.edit('code').getCursorPosition(),scroll:document.querySelector('#document-content').scrollTop}));
  const stats=(await(await fetch(base+'/api/state')).json()).problems[0].stats;
  async function open(){await page.locator('#visualize').click();await page.waitForSelector('#viz-generate');}
  async function generate(){const pending=page.waitForResponse(r=>r.url().endsWith('/api/visualizations')&&r.request().method()==='POST');await page.locator('#viz-generate').click();const result=await(await pending).json();await page.waitForFunction(()=>!document.querySelector('#viz-generate').disabled);return result;}
  await open();assert.equal(await page.locator('dialog').evaluate(el=>el.contains(document.activeElement)),true);
  const sample=await generate();assert.equal(sample.status,'READY',sample.error);assert.equal(sample.stdout.trim(),'4');
  assert((await page.locator('#viz-step').textContent()).startsWith('1 /'));assert.equal(await page.locator('#viz-play').textContent(),'播放');
  await page.locator('#viz-mode').selectOption('manual');await page.locator('#viz-input').fill('6\n2 4 6 1 3 5\n');
  const result=await generate();assert.equal(result.status,'READY',result.error);assert.equal(result.stdout.trim(),'6');
  await page.locator('#viz-next-count').click();
  assert.deepEqual(await page.locator('.viz-pairs__item').allTextContents(),['(2, 1)','(4, 1)','(6, 1)']);
  assert.equal(await page.locator('.viz-lesson__count b').textContent(),'+3');
  await page.waitForFunction(()=>{
   const host=document.querySelector('.viz-source__scroll').getBoundingClientRect();
   const active=document.querySelector('.viz-source li[data-active="true"]').getBoundingClientRect();
   return active.top>=host.top && active.bottom<=host.bottom;
  });
  assert((await page.locator('.viz-source li[data-active="true"]').textContent()).includes('cnt += mid - ll + 1;'));
  const state=()=>page.evaluate(()=>JSON.stringify({step:document.querySelector('#viz-step').textContent,pairs:document.querySelector('.viz-pairs').textContent,stage:document.querySelector('#viz-stage').textContent,selected:[...document.querySelectorAll('#viz-stage td')].map(x=>[x.textContent,x.dataset.selected,x.dataset.patched])}));
  const counted=await state();await page.locator('#viz-prev').click();await page.locator('#viz-next').click();assert.equal(await state(),counted);
  await screenshot(page,'dark.png');
  await page.locator('#viz-stage').focus();await page.keyboard.press('End');assert.equal(await page.locator('.viz-lesson__count strong').textContent(),'6');
  await page.locator('#viz-restart').click();await page.locator('#viz-speed').selectOption('4');await page.locator('#viz-play').click();
  await page.waitForFunction(()=>!document.querySelector('#viz-step').textContent.startsWith('1 /'));await page.locator('#viz-play').click();const paused=await page.locator('#viz-step').textContent();await page.waitForTimeout(500);assert.equal(await page.locator('#viz-step').textContent(),paused);
  await page.keyboard.press('Escape');assert.equal(await page.locator('dialog').count(),0);
  const after=await page.evaluate(()=>({code:ace.edit('code').getValue(),cursor:ace.edit('code').getCursorPosition(),scroll:document.querySelector('#document-content').scrollTop}));assert.deepEqual(after,before);
  assert((await fs.readFile(path.join(problem,'attempts/001.cpp'),'utf8')).includes('retained draft'));
  assert.deepEqual((await(await fetch(base+'/api/state')).json()).problems[0].stats,stats);
  console.log('PASS sample/manual C++ execution, triple inversion, source line, replay, playback, draft/cursor/scroll preservation, unchanged statistics');
  await fs.writeFile(path.join(problem,'visualize.cpp'),source+'\n// modified later\n');
  await open();await page.waitForFunction(()=>document.querySelector('#viz-history').options.length>=3);
  await page.locator('#viz-history').selectOption(result.id);await page.waitForSelector('#viz-stage');
  assert(!(await page.locator('.viz-source').textContent()).includes('modified later'));
  assert.equal(await page.locator('#viz-input').inputValue(),result.input);
  await page.locator('#viz-next-count').click();
  await page.keyboard.press('Escape');await page.locator('#theme-toggle').click();await open();await page.waitForFunction(()=>document.querySelector('#viz-history').options.length>=3);
  await page.locator('#viz-history').selectOption(result.id);await page.waitForSelector('#viz-stage');await page.locator('#viz-next-count').click();
  await screenshot(page,'light.png');
  await page.keyboard.press('Escape');await page.locator('#theme-toggle').click();await open();await page.waitForFunction(()=>document.querySelector('#viz-history').options.length>=3);await page.locator('#viz-history').selectOption(result.id);await page.waitForSelector('#viz-stage');await page.locator('#viz-next-count').click();
  await page.emulateMedia({reducedMotion:'reduce'});
  for(const size of [{width:375,height:812},{width:812,height:375},{width:720,height:500}]){
   await page.setViewportSize(size);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.locator('.viz-lesson').scrollIntoViewIfNeeded();
   assert.equal(await page.locator('.viz-lesson').isVisible(),true);
   assert((await page.locator('.viz-dialog__body').boundingBox()).height>180,'teaching body must not collapse');
   await screenshot(page,`lesson-${size.width}.png`);
   await page.locator('#viz-stage').scrollIntoViewIfNeeded();
   assert((await page.locator('#viz-stage').boundingBox()).height>80);
   await screenshot(page,`arrays-${size.width}.png`);
   await page.locator('.viz-source').scrollIntoViewIfNeeded();
   await page.waitForFunction(()=>{
    const host=document.querySelector('.viz-source__scroll').getBoundingClientRect();
    const active=document.querySelector('.viz-source li[data-active="true"]').getBoundingClientRect();
    return active.top>=host.top && active.bottom<=host.bottom;
   });
   await page.locator('#viz-next').click();await page.locator('#viz-prev').click();assert.equal(await state(),counted);
   await page.locator('#viz-stage').focus();await page.keyboard.press('ArrowLeft');await page.keyboard.press('ArrowRight');assert.equal(await state(),counted);
   await page.locator('.viz-controls').scrollIntoViewIfNeeded();
   await screenshot(page,`controls-${size.width}.png`);
   await page.keyboard.press('Tab');assert.equal(await page.locator('dialog').evaluate(el=>el.contains(document.activeElement)),true);
  }
  await page.setViewportSize({width:1440,height:1000});
  // Closing while compiling must not resurrect a modal; completed snapshots remain available.
  const generating=page.waitForResponse(r=>r.url().endsWith('/api/visualizations')&&r.request().method()==='POST');
  await page.locator('#viz-generate').click();await page.keyboard.press('Escape');
  const closedResult=await(await generating).json();assert.equal(closedResult.status,'READY');assert.equal(await page.locator('dialog').count(),0);
  await open();await page.waitForFunction(id=>[...document.querySelector('#viz-history').options].some(option=>option.value===id),closedResult.id);
  await page.locator('#viz-history').selectOption(closedResult.id);await page.waitForSelector('#viz-stage');
  await page.locator('#viz-mode').selectOption('manual');const bad='21\n'+'1 '.repeat(21);await page.locator('#viz-input').fill(bad);const invalid=await generate();assert.equal(invalid.status,'INPUT_ERROR');assert.equal(await page.locator('#viz-input').inputValue(),bad);assert.equal(await page.locator('#viz-play').isDisabled(),true);assert.equal(await page.locator('[role="alert"]').last().isVisible(),true);
  await page.keyboard.press('Escape');
  await page.route('**/api/problem?*',async route=>{const response=await route.fetch();const data=await response.json();delete data.visualization;await route.fulfill({response,json:data});});
  await page.locator('#refresh').click();await page.waitForFunction(()=>!document.querySelector('#refresh').disabled);
  assert.equal(await page.locator('#visualize').isDisabled(),true);assert((await page.locator('#visualize').getAttribute('title')).includes('重启'));
  assert.deepEqual((await(await fetch(base+'/api/state')).json()).problems[0].stats,stats);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log('PASS historical snapshots, light/dark/mobile, reduced motion, invalid input without truncation, legacy server hint; no browser errors or external requests');
 }finally{if(browser)await browser.close();if(server.exitCode===null && server.signalCode===null){const stopped=new Promise(r=>server.once('exit',r));server.kill('SIGINT');await stopped;}await fs.rm(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
