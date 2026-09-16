let data=null, activeEvent=null, submitting=false;
const filters={query:'',source:'',status:''};
let glassLevel=52;
const icons={overview:'▦',events:'◇',coverage:'▤',history:'◷'};

const labels={wecom:'企微社群',wechat_export:'民间微信群＊',voc:'公域 VOC',suggestions:'意见建议'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number(n||0).toLocaleString('zh-CN');
function review(e){return data.reviews?.[e.id]||{decision:'pending',level:e.level||''}}
function stateLabel(e){return {pending:'待核验',confirmed:'已确认',rejected:'已驳回'}[review(e).decision]}
function draw(){
 const total=data.sources.reduce((n,s)=>n+s.imported,0),analyzed=data.sources.reduce((n,s)=>n+s.analyzed,0);
 const pending=data.events.filter(e=>review(e).decision==='pending').length;
 const outbox=(data.simulated_outbox||[]).length;
 const dates=Array.from({length:31},(_,i)=>'2026-08-'+String(i+1).padStart(2,'0'));
 const daily=dates.map(day=>data.daily.filter(r=>r.day===day).reduce((n,r)=>n+r.candidates,0)),max=Math.max(1,...daily);
 document.querySelector('#app').innerHTML=`<section class="blue-v2"><aside class="b-sidebar"><a href="#" class="b-brand"><span class="b-logo">9</span>ninebot<span class="brand-dot">.</span><span class="b-brand-sub">舆情洞察工作空间</span></a><div class="nav-caption">WORKSPACE</div><nav aria-label="工作空间"><button class="b-nav active" data-scroll="overview"><span class="nav-icon" aria-hidden="true">${icons.overview}</span>总览</button><button class="b-nav" data-scroll="events"><span class="nav-icon" aria-hidden="true">${icons.events}</span>风险事件</button><button class="b-nav" data-scroll="coverage"><span class="nav-icon" aria-hidden="true">${icons.coverage}</span>数据覆盖</button><button class="b-nav" data-scroll="history"><span class="nav-icon" aria-hidden="true">${icons.history}</span>核验记录</button></nav><div class="sidebar-poem"><span class="small-orb" aria-hidden="true"></span><h3>每一种声音，<br>都值得被听见。</h3><p>连接用户反馈<br>让关切得到回应</p><small>LISTEN. UNDERSTAND. ACT.</small></div><div class="glass-control"><label for="glass-level">◉ &nbsp; 玻璃透明度</label><input id="glass-level" type="range" min="25" max="85" value="${glassLevel}"><div><span>通透</span><span>柔和</span></div></div><div class="b-sidebar-bottom"><span class="profile-avatar">9</span><div>服务运营<small>8月历史回放 · 通知仅模拟</small></div></div></aside><div class="b-main"><header class="b-toolbar"><span class="breadcrumb">九号电动 <i>/</i> 八月历史回放</span><span class="b-account"><i></i>内部评审 · 历史数据</span></header><div class="b-content" id="overview"><section class="b-hero"><div class="b-hero-copy"><span class="b-kicker">THE VOICE BEHIND EVERY RIDE</span><h1>听见每一程，<br><span>洞察每一种声音。</span></h1><p>四个数据来源，一条核验流程。<br>从用户反馈，到有依据的判断。</p><button class="b-dark-button" data-scroll="events">查看风险事件 →</button></div><div class="hero-art" aria-hidden="true"><div class="glass-orb"></div><div class="glass-orbit"></div><span class="floating-tag">✧ CONNECTING VOICES</span><div class="floating-card"><small>待人工核验</small><b>${num(pending)}</b><span>项候选</span></div><div class="art-caption">A LITTLE CLARITY. EVERY DAY.</div></div></section><div class="section-title"><h2>舆情脉搏</h2><span class="b-date">2026.08.01 — 08.31</span></div><section class="sources-section"><div class="actual-sources">${['wecom','wechat_export','voc','suggestions'].map(key=>{const s=data.sources.find(s=>s.source===key)||{};return `<div class="actual-source"><i class="source-dot ${key}"></i><strong>${esc(labels[key]||key)}</strong><span>${s.imported==null?'—':num(s.imported)}</span><small>条</small></div>`}).join('')}</div><p class="source-note">＊已排除已知官方群重叠；剩余群的民间归属仍待核实。</p></section><div class="pipeline"><span>四来源输入</span>→<span>候选筛选</span>→<span>公司模型分析</span>→<span>人工核验</span>→<span>模拟预警</span></div><div class="b-metrics">${[['导入内容',total,'全月可用文本，不代表均已分析'],['已分析内容',analyzed,'安全词优先＋普通候选抽样'],['待核验候选',pending,'模型候选与规则线索，均待核验'],['模拟通知',outbox,'确认 R1/R2 后生成']].map(([s,n,t],i)=>`<section class="b-card b-stat"><i class="stat-icon" aria-hidden="true">${['▤','✧','◇','◷'][i]}</i><span>${s}</span><strong>${num(n)}</strong><small class="b-blue">${t}</small></section>`).join('')}</div><div class="b-middle"><section class="b-card"><div class="b-panel-head"><h2>每日候选量</h2><span class="b-tag">输入筛选统计</span></div><div class="daily-bars">${daily.map((n,i)=>`<div class="day-bar" style="height:${Math.max(1,n/max*100)}%" title="${dates[i]}：${n}条候选"></div>`).join('')}</div><div class="chart-labels"><span>08.01</span><span>08.08</span><span>08.15</span><span>08.22</span><span>08.31</span></div><p class="b-note">候选量不是风险事件量，也不能用于计算全网负面率。</p></section><section class="b-card" id="history"><div class="b-panel-head"><h2>核验记录</h2><button class="b-link" id="refresh">刷新</button></div>${data.history.length?data.history.slice(0,4).map(r=>`<div class="review-row">${esc(r.level)} · ${r.decision==='confirmed'?'确认':'驳回'}<small>${esc(r.note)}</small><small>${esc(r.updated_at)}</small></div>`).join(''):'<p class="b-note">尚无人工作出核验结论。打开候选、阅读证据并提交意见后，记录会保存在服务器。</p>'}<p class="b-note">${num(data.r4)} 条已分析内容为 R4，不进入风险候选列表。模拟通知只是待发送记录，不联系用户或群。</p></section></div><section class="b-card b-events" id="events"><div class="b-panel-head"><h2>风险候选与证据</h2><span class="b-tag">模型候选 · 待分析线索</span></div><div class="actual-tools"><input id="search" value="${esc(filters.query)}" placeholder="搜索主题、车型、问题" aria-label="搜索风险候选"><select id="filter" aria-label="按来源筛选"><option value="">全部来源</option>${Object.entries(labels).map(([k,v])=>`<option value="${k}" ${filters.source===k?'selected':''}>${v}</option>`).join('')}</select><select id="status-filter" aria-label="按核验状态筛选">${[['','全部状态'],['pending','待核验'],['confirmed','已确认'],['rejected','已驳回']].map(([k,v])=>`<option value="${k}" ${filters.status===k?'selected':''}>${v}</option>`).join('')}</select></div><div class="b-table-wrap"><table><thead><tr><th>问题与车型</th><th>日期 / 来源</th><th>等级</th><th>核验状态</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table></div><p id="empty" class="b-empty" hidden>没有匹配的风险候选。</p></section><section class="b-card b-events" id="coverage"><div class="b-panel-head"><h2>数据覆盖与分析进度</h2><span class="b-tag">真实运行统计</span></div><div class="coverage-table"><table><thead><tr><th>来源</th><th>导入</th><th>候选</th><th>已分析</th><th>有数据天数</th><th>日期范围</th></tr></thead><tbody>${data.sources.map(s=>`<tr><td>${esc(labels[s.source]||s.source)}</td><td>${num(s.imported)}</td><td>${num(s.candidates)}</td><td>${num(s.analyzed)}${s.source==='suggestions'&&Number(s.analyzed)===0?'<small class="rule-note">尚未调用模型 · 候选由关键词／原投诉类型筛选</small>':''}</td><td>${s.days}/31</td><td>${esc(s.first?.slice(0,10)||'—')} ～ ${esc(s.last?.slice(0,10)||'—')}</td></tr>`).join('')}</tbody></table></div><div class="boundaries"><strong>数据与解释边界</strong><ul>${data.limits.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>${Object.entries(data.audit).map(([key,a])=>`<p>${esc(labels[key]||key)}：${esc(a.coverage)}</p>`).join('')}<p>分析失败：${num(data.analysis.find(x=>x.status==='failed')?.n)} 条。尚未分析的候选不视为已排除风险。</p></div></section><footer class="b-footer">数据快照生成：${esc(data.generated_at)} · 真实原文与来源字段仅限内部核验。</footer></div></div></section>`;
 document.querySelector('#search').oninput=()=>{filters.query=document.querySelector('#search').value;rows()};document.querySelector('#filter').onchange=()=>{filters.source=document.querySelector('#filter').value;rows()};document.querySelector('#status-filter').onchange=()=>{filters.status=document.querySelector('#status-filter').value;rows()};document.querySelector('#glass-level').oninput=ev=>{glassLevel=Number(ev.target.value);document.documentElement.style.setProperty('--glass-alpha',glassLevel/100)};document.querySelector('#refresh').onclick=()=>load();rows();mountWorkspace();
}

// Server records are authoritative. UI state never supplies substitute records.
const workspace={page:'overview',options:null,optionsError:'',messages:null,messageError:'',messageLoading:false,messageRequest:0,messagePage:1,applied:null,report:null,schedules:null,scheduleError:'',busy:false};
const initialFilters={start:'2026-08-01',end:'2026-08-31',source:'',channel:'',topic:'',tag_id:'',q:''};
let browseFilters={...initialFilters},reportFilters={...initialFilters};
const periods={daily:'日报',weekly:'周报',monthly:'月报',custom:'自定义周期'};
const $=s=>document.querySelector(s);
function valueText(v){return v==null||v===''?'未提供':typeof v==='object'?JSON.stringify(v,null,2):String(v)}
function safeValue(v){const text=valueText(v);try{const u=new URL(text);if(['http:','https:'].includes(u.protocol))return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`}catch{}return esc(text)}
function fieldList(fields){if(!fields||typeof fields!=='object'||Array.isArray(fields))fields={'原始字段':fields};return `<dl class="record-fields">${Object.entries(fields).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${safeValue(v)}</dd></div>`).join('')}</dl>`}
function tags(items){const list=Array.isArray(items)?items:[];return list.map(t=>`<span class="taxonomy-chip">${esc(t.path||[t.level1,t.level2,t.level3,t.level4].filter(Boolean).join(' / ')||t.id)}</span>`).join('')+(list.length?'<small class="taxonomy-rule-note">分类匹配 · 词面规则待核实</small>':'')}
function isUnanalysed(e){return ['unanalysed','unanalyzed'].includes(e.analysis_status)}
function rows(){
 const q=filters.query.trim().toLowerCase();
 const events=data.events.filter(e=>(!filters.source||e.source===filters.source)&&(!filters.status||review(e).decision===filters.status)&&[e.issue,e.topic,e.vehicle,...(e.taxonomy||[]).map(t=>t.path)].some(s=>String(s??'').toLowerCase().includes(q)));
 $('#rows').innerHTML=events.map(e=>{const r=review(e);return `<tr><td>${esc(e.issue||'待分析线索')}<small>${esc(e.vehicle||'')} ${esc(e.topic||'')}</small>${isUnanalysed(e)?'<small class="rule-note">规则线索 · 非模型结论</small>':''}${tags(e.taxonomy)}</td><td>${esc(e.day)}<small>${esc(labels[e.source]||e.source)}</small></td><td>${isUnanalysed(e)?'<span class="state-pill">待分析线索</span>':`<span class="b-pill ${r.level==='R1'?'red':'amber'}">${esc(r.level||'未提供')}</span>`}${isUnanalysed(e)&&r.decision!=='pending'?`<small>人工核验：${esc(r.level)}</small>`:''}</td><td><span class="state-pill ${esc(r.decision)}">${esc(stateLabel(e)||r.decision)}</span></td><td><button class="b-link" data-event="${esc(e.id)}">查看原文 →</button></td></tr>`}).join('');
 $('#empty').hidden=events.length>0;
}
function originalRecord(v,excerpt=false){
 const available=v.original_available!==false&&v.raw_text!=null;
 return `<article class="original-record"><div class="evidence-meta">${esc(v.time||'时间未提供')} · ${esc(v.source_name||labels[v.source]||'来源未提供')}</div>${fieldList({'真实群名':v.group_name,'渠道':v.channel,'平台':v.platform})}<h3>${!available?'原始正文未提供':excerpt?'原文摘录（最多500字）':'完整原文'}</h3>${available?`<blockquote>${esc(v.raw_text)}</blockquote>`:'<p class="notice warning">接口未提供原始正文，请核对原始记录。</p>'}${v.original_available!==false&&v.raw_quote?`<h3>${excerpt?'原始引用摘录（最多500字）':'原始引用'}</h3><blockquote>${esc(v.raw_quote)}</blockquote>`:''}<details><summary>原始记录字段</summary>${fieldList({'记录 ID':v.message_id??v.id,'来源名称':v.source_name,'作者':v.author,'原生 ID':v.native_id,'来源文件':v.source_file,'来源行':v.source_row})}${fieldList(v.raw_fields||v.raw_json||{})}</details>${excerpt?`<button class="b-link" data-full-message="${esc(v.message_id??v.id)}">读取原始记录 →</button>`:''}</article>`;
}
function showDialog(html,opener){activeEvent=opener;$('#detail-content').innerHTML=html;if(!$('#details').open)$('#details').showModal()}
function detail(id){
 const e=data.events.find(x=>x.id===id);if(!e)return;
 const r=review(e),unanalysed=isUnanalysed(e);
 showDialog(`<span class="b-kicker">${esc(labels[e.source]||e.source)} / ${esc(e.day)}</span><h2 id="event-title">${esc(e.issue||'待分析线索')} ${esc(e.vehicle||'')}</h2><div class="tag-list">${tags(e.taxonomy)}</div>${unanalysed?'<p class="notice">待分析线索 · 规则筛选，尚无模型结论。</p>':''}<section class="original-section"><h3>真实来源与原文 · ${(e.evidence||[]).length} 条记录</h3>${(e.evidence||[]).map(v=>originalRecord(v)).join('')||'<p class="notice">未返回原始证据记录。</p>'}</section><section class="analysis-section"><h3>${unanalysed?'分析状态':'模型判断'}</h3>${unanalysed?'<p>尚未进行模型分析。人工核验时请依据上方原始记录。</p>':`<p>${esc(e.summary||'模型摘要未提供')}</p>${(e.evidence||[]).map(v=>`<div class="analysis-record">${fieldList({'意图':v.intent,...(v.confidence==null?{}:{'模型自评置信度':v.confidence}),'判断依据':v.reason})}<details><summary>模型分析时的上下文（预处理）</summary><blockquote>${esc(v.text||'未提供')}</blockquote>${v.quote_text?`<blockquote>${esc(v.quote_text)}</blockquote>`:''}<pre>${esc(typeof v.context_json==='string'?v.context_json:JSON.stringify(v.context_json||{},null,2))}</pre></details></div>`).join('')}`}</section><form class="review-form" id="review-form"><h3>人工核验</h3><label>最终等级 <select name="level" required><option value="">请选择等级</option>${['R1','R2','R3','R4'].map(x=>`<option value="${x}" ${(!unanalysed||r.decision!=='pending')&&r.level===x?'selected':''}>${x}</option>`).join('')}</select></label><label class="note-label" for="review-note">核验依据</label><textarea id="review-note" name="note" maxlength="1000" required placeholder="依据真实原文填写判断依据或驳回原因">${esc(r.note||'')}</textarea><div class="actions"><button value="confirmed">确认候选</button><button value="rejected" class="reject">驳回候选</button></div><p class="review-status" id="review-status" role="status"></p></form>`,id);
 $('#review-form').onsubmit=async ev=>{
  ev.preventDefault();if(submitting)return;
  const form=ev.target,f=new FormData(form),status=$('#review-status'),decision=ev.submitter?.value;
  if(!decision)return;if(!String(f.get('note')||'').trim()){status.textContent='请填写核验依据。';return;}
  submitting=true;form.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='正在保存核验意见…';
  try{await api('api/review',{event_id:id,decision,level:f.get('level'),note:f.get('note')});const refreshed=await load();status.textContent=refreshed?'已保存核验意见。没有发送真实通知。':'核验意见已保存，列表刷新失败，请稍后刷新核对。';}
  catch(err){status.textContent=err.message;}
  finally{submitting=false;form.querySelectorAll('button').forEach(b=>b.disabled=false);}
 };
}
async function api(url,body){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),180000);
 try{
  const response=await fetch(url,{cache:'no-store',signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':data?.csrf||''},body:JSON.stringify(body)})});
  let result;try{result=await response.json()}catch{throw Error('服务返回格式异常，请稍后重试。')}
  if(!response.ok)throw Error(result.error==='Not found'?'当前服务尚未提供此接口，请更新本地服务后重试。':result.error||`请求失败（${response.status}），请稍后重试。`);return result;
 }catch(err){if(err.name==='AbortError')throw Error('请求超时，请刷新状态核对后再重试。');throw err}
 finally{clearTimeout(timeout)}
}
function selectedOptions(items,value,key='id',label='label'){
 return (items||[]).map(item=>{const id=typeof item==='string'?item:item[key];const name=typeof item==='string'?item:item[label]??item.path??id;return `<option value="${esc(id)}" ${String(value)===String(id)?'selected':''}>${esc(name)}</option>`}).join('');
}
function filterForm(prefix,f){
 const o=workspace.options||{};
 return `<div class="filter-grid"><label>开始日期<input type="date" name="start" value="${esc(f.start)}" min="${esc(o.range?.start||'')}" max="${esc(o.range?.end||'')}" required></label><label>结束日期<input type="date" name="end" value="${esc(f.end)}" min="${esc(o.range?.start||'')}" max="${esc(o.range?.end||'')}" required></label><label>消息来源<select name="source"><option value="">全部来源</option>${selectedOptions(o.sources,f.source)}</select></label><label>渠道<select name="channel"><option value="">全部渠道</option>${selectedOptions(o.channels,f.channel)}</select></label><label>话题<select name="topic"><option value="">全部话题</option>${selectedOptions(o.topics,f.topic)}</select></label><label>分类标签<select name="tag_id"><option value="">全部标签</option>${selectedOptions(o.taxonomy,f.tag_id,'id','path')}</select></label><label class="query-field">关键词<input name="q" value="${esc(f.q)}" placeholder="搜索真实原文" type="search"></label></div>`;
}
function readFilters(form){const f=Object.fromEntries(new FormData(form));return Object.fromEntries(Object.keys(initialFilters).map(k=>[k,String(f[k]||'').trim()]))}
function validateFilters(f){if(!f.start||!f.end||f.start>f.end)throw Error('请选择有效时间范围，结束日期不能早于开始日期。');return f}
function filterSummary(f){return [f.start+' — '+f.end,f.source?labels[f.source]||f.source:'全部来源',f.channel||'全部渠道',f.topic||'全部话题',f.tag_id?(workspace.options?.taxonomy||[]).find(t=>String(t.id)===String(f.tag_id))?.path||f.tag_id:'全部标签',f.q?`关键词：${f.q}`:''].filter(Boolean).join(' · ')}
function mountWorkspace(){
 const nav=$('.b-sidebar nav');
 nav.insertAdjacentHTML('beforeend',`<button class="b-nav" data-scroll="browse"><span class="nav-icon" aria-hidden="true">▤</span>数据浏览</button><button class="b-nav" data-scroll="reports"><span class="nav-icon" aria-hidden="true">◷</span>报告中心</button><button class="b-nav" data-scroll="taxonomy"><span class="nav-icon" aria-hidden="true">⌘</span>分类标签</button>`);
 const content=$('.b-content'),pane=document.createElement('div');pane.id='overview-pane';while(content.firstChild)pane.append(content.firstChild);content.append(pane);
 content.insertAdjacentHTML('beforeend',`<section id="browse" class="workspace-pane" hidden><div class="workspace-heading"><div><span class="b-kicker">ORIGINAL VOICES</span><h1>数据浏览</h1><p>按时间、渠道与话题查阅真实记录，导出完整筛选结果。</p></div><span class="b-tag">8月历史数据</span></div><div id="browse-content"></div></section><section id="reports" class="workspace-pane" hidden><div class="workspace-heading"><div><span class="b-kicker">REPORT STUDIO</span><h1>报告中心</h1><p>专项周期报告 · 四来源历史自动获取模拟</p></div><span class="b-tag">历史模拟</span></div><div id="reports-content"></div></section><section id="taxonomy" class="workspace-pane" hidden><div class="workspace-heading"><div><span class="b-kicker">CLASSIFICATION</span><h1>分类标签</h1><p>分类层级与适用标签以服务端返回为准。</p></div><div class="company-labels"><span>通用</span><span>电动</span></div></div><div id="taxonomy-content"></div></section>`);
 renderWorkspace();showPage(workspace.page,false);
}
function showPage(page,scroll=true){
 workspace.page=page;const extended=['browse','reports','taxonomy'].includes(page);
 $('#overview-pane').hidden=extended;for(const id of ['browse','reports','taxonomy'])$('#'+id).hidden=id!==page;
 document.querySelectorAll('.b-nav').forEach(b=>{b.classList.toggle('active',b.dataset.scroll===page);if(b.dataset.scroll===page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
 if(scroll)(page==='overview'?$('.b-content'):$('#'+page))?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
 if(page==='browse'&&workspace.options&&!workspace.messages&&!workspace.messageLoading&&!workspace.messageError)fetchMessages(1);
 if(page==='reports'&&workspace.options&&workspace.schedules===null&&!workspace.scheduleError)loadSchedules();
}
function renderWorkspace(){
 for(const id of ['browse','reports','taxonomy']){const target=$('#'+id+'-content');if(!workspace.options){target.innerHTML=workspace.optionsError?`<div class="notice warning" role="alert">${esc(workspace.optionsError)} <button class="b-link" data-action="options-retry">重新读取选项</button></div>`:'<p class="notice" role="status">正在读取四来源与分类选项…</p>';}}
 if(!workspace.options)return;renderBrowse();renderReports();renderTaxonomy();
}
async function loadOptions(){
 workspace.optionsError='';if(data)renderWorkspace();
 try{workspace.options=await api('api/report-options');for(const s of workspace.options.sources||[])labels[s.id]=s.label;
  if(workspace.options.range){browseFilters={...browseFilters,...workspace.options.range};reportFilters={...reportFilters,...workspace.options.range};}
 }catch(err){workspace.optionsError=err.message}
 if(data){renderWorkspace();showPage(workspace.page,false)}
}
function summaryCards(s){return `<div class="summary-grid">${[['匹配记录','total'],['已分析','analyzed_success'],['未分析','unanalyzed'],['其他分析状态','analysis_other'],['模型风险记录','analyzed_risk']].map(([label,key])=>`<div><span>${label}</span><strong>${s?.[key]==null?'—':num(s[key])}</strong></div>`).join('')}</div>`}
function renderBrowse(){
 $('#browse-content').innerHTML=`<section class="b-card"><form id="browse-form">${filterForm('browse',browseFilters)}<div class="work-actions"><button class="primary-button" type="submit">应用筛选</button><button type="button" data-action="browse-reset">重置</button><span class="b-note">日期包含开始及结束当天</span></div></form><p id="browse-form-status" class="notice" role="status"></p></section><section class="b-card results-card"><div class="b-panel-head"><h2>原始消息记录</h2><div class="work-actions"><button data-export="csv" ${!workspace.applied||workspace.messageLoading||workspace.messageError?'disabled':''}>导出 CSV</button><button data-export="json" ${!workspace.applied||workspace.messageLoading||workspace.messageError?'disabled':''}>导出 JSON</button><button data-action="to-report" ${!workspace.applied?'disabled':''}>用此筛选生成报告</button></div></div><p id="export-status" class="notice" role="status"></p><div id="message-results"></div></section>`;
 $('#browse-form').onsubmit=ev=>{ev.preventDefault();try{browseFilters=validateFilters(readFilters(ev.target));fetchMessages(1)}catch(err){$('#browse-form-status').textContent=err.message}};
 renderMessages();
}
function renderMessages(){
 const el=$('#message-results');if(!el)return;
 if(workspace.messageLoading){el.innerHTML='<p class="notice" role="status">正在读取真实消息…</p>';return}
 if(workspace.messageError){el.innerHTML=`<p class="notice warning" role="alert">${esc(workspace.messageError)} <button data-action="messages-retry">重新读取</button></p>`;return}
 const m=workspace.messages;if(!m){el.innerHTML='<p class="notice">应用筛选后查看真实记录。</p>';return}
 const pages=Math.max(1,Math.ceil(m.total/(m.page_size||30)));
 el.innerHTML=`<p class="applied-filters">当前结果：${esc(filterSummary(workspace.applied))}</p>${summaryCards(m.summary)}<p class="b-note">风险记录数仅指已成功分析的 R1–R3；未分析记录不代表无风险。导出包含当前结果的全部 ${num(m.total)} 条记录。</p><div class="message-list">${m.items.map((v,i)=>`<article class="message-card"><div class="message-top"><span class="source-badge">${esc(v.source_name||labels[v.source]||v.source)}</span><span>${esc(v.time)}</span><span class="state-pill">${v.analysis_status==='ok'?`已分析 ${esc(v.analysis_level||'')}`:'未分析或其他状态'}</span></div><p class="message-channel">${esc(v.group_name||v.channel||v.platform||'来源字段未提供')}</p><blockquote>${v.original_available===false||v.raw_text==null?'接口未提供原始正文':esc(v.raw_text)}</blockquote><div class="message-bottom"><span>话题（词面规则待核实）：${esc(v.topic||'未分类')}</span><button class="b-link" data-message-index="${i}">查看原文与记录字段 →</button></div></article>`).join('')||'<p class="b-empty">当前筛选没有匹配消息，可调整日期、渠道或关键词。</p>'}</div><div class="pagination"><button data-page="${workspace.messagePage-1}" ${workspace.messagePage<=1?'disabled':''}>上一页</button><span>第 ${workspace.messagePage} / ${pages} 页 · ${num(m.total)} 条</span><button data-page="${workspace.messagePage+1}" ${workspace.messagePage>=pages?'disabled':''}>下一页</button></div>`;
}
async function fetchMessages(page){
 const request=++workspace.messageRequest;workspace.messageLoading=true;workspace.messageError='';workspace.messagePage=page;
 const selected={...browseFilters};renderBrowse();
 try{const result=await api('api/messages?'+new URLSearchParams({...selected,page,page_size:30}));if(request!==workspace.messageRequest)return;workspace.messages=result;workspace.applied=selected;}
 catch(err){if(request!==workspace.messageRequest)return;workspace.messageError=err.message;workspace.messages=null}
 finally{if(request===workspace.messageRequest){workspace.messageLoading=false;renderBrowse()}}
}
function reportLinks(id){return `<div class="work-actions"><button data-report-export="html" data-report-id="${esc(id)}">导出 HTML / 打印 PDF</button><button data-report-export="json" data-report-id="${esc(id)}">导出 JSON</button></div>`}
function renderReports(){
 const target=$('#reports-content');if(!target)return;
 target.innerHTML=`<div class="notice historical-notice">使用真实 8 月历史记录模拟四来源获取与周期报告。保存配置后，点击“模拟运行”产出历史报告；通知仅模拟。</div><section class="b-card"><form id="report-form"><div class="report-basics"><label>报告标题<input name="title" required maxlength="120" value="${esc(workspace.reportTitle||'8月用户反馈统计报表')}"></label><label>报告周期<select name="period">${selectedOptions(Object.entries(periods).map(([id,label])=>({id,label})),workspace.period||'monthly')}</select></label></div>${filterForm('report',reportFilters)}<div class="work-actions"><button class="primary-button" type="submit" ${workspace.busy?'disabled':''}>生成统计报表</button><label class="schedule-name">自动报告名称<input name="name" maxlength="120" value="${esc(workspace.scheduleName||'')}" placeholder="例如：8月每周用户反馈"></label><button type="button" data-action="save-schedule" ${workspace.busy?'disabled':''}>保存周期配置</button></div><p id="report-status" class="notice" role="status">${esc(workspace.reportStatus||'')}</p></form></section><section id="generated-report" class="b-card results-card"></section><section class="b-card results-card"><div class="b-panel-head"><h2>自动报告配置与运行</h2><button class="b-link" data-action="schedules-refresh">刷新记录</button></div><div id="schedules-list"></div></section>`;
 $('#report-form').onsubmit=ev=>{ev.preventDefault();submitReport(false)};
 $('#report-form').oninput=()=>captureReportForm();
 renderGeneratedReport();renderSchedules();renderTopicStudio();
}
function captureReportForm(){const form=$('#report-form');if(!form)return;const values=new FormData(form);reportFilters=readFilters(form);workspace.reportTitle=values.get('title');workspace.period=values.get('period');workspace.scheduleName=values.get('name')}
async function submitReport(schedule){
 if(workspace.busy)return;const form=$('#report-form');if(!form.reportValidity())return;captureReportForm();
 try{validateFilters(reportFilters);if(schedule&&!String(workspace.scheduleName||'').trim())throw Error('请填写自动报告名称。')}catch(err){$('#report-status').textContent=err.message;return}
 workspace.busy=true;workspace.reportStatus=schedule?'正在保存周期配置…':'正在根据真实记录生成报告…';renderReports();
 try{
  const payload={title:String(workspace.reportTitle).trim(),period:workspace.period,filters:{...reportFilters}};
  if(schedule){await api('api/report-schedules',{...payload,name:workspace.scheduleName.trim()});workspace.reportStatus='周期配置已保存，可手动模拟运行 8 月历史周期。';await loadSchedules()}
  else{const result=await api('api/reports/generate',payload);workspace.report=result.report;workspace.reportStatus='统计报表已生成。';}
 }catch(err){workspace.reportStatus=err.message}
 finally{workspace.busy=false;renderReports()}
}
function renderGeneratedReport(){
 const el=$('#generated-report');if(!el)return;const r=workspace.report;
 if(!r){el.innerHTML='<h2>报告预览</h2><p class="notice">选择时间范围与主题后生成统计报表。周报按自然周切分，首尾可为不完整周。</p>';return}
 el.innerHTML=`<div class="b-panel-head"><h2>${esc(r.title)}</h2><span class="b-tag">${esc(periods[r.period]||r.period)}</span></div><p class="applied-filters">${esc(filterSummary(r.filters))}</p><p class="notice">${esc(r.notice||'历史模拟报告')}</p>${summaryCards(r.summary)}<h3>四来源覆盖</h3><div class="report-sources">${(r.sources||[]).map(s=>`<div><strong>${esc(labels[s.source]||s.source)}</strong><span>${num(s.total)} 条</span><small>已分析 ${num(s.analyzed_success)} · 未分析 ${num(s.unanalyzed)}</small></div>`).join('')}</div>${r.topics?.length?`<h3>话题分布 · 词面规则待核实</h3><div class="report-topics">${r.topics.map(t=>`<div><strong>${esc(t.topic)}</strong><span>${num(t.total)} 条</span><small>模型风险 ${num(t.analyzed_risk)} · 未分析 ${num(t.unanalyzed)}</small></div>`).join('')}</div>`:''}<h3>周期统计</h3><div class="b-table-wrap"><table class="report-table"><thead><tr><th>周期</th><th>记录</th><th>已分析</th><th>未分析</th><th>模型风险</th></tr></thead><tbody>${(r.buckets||[]).map(b=>`<tr><td>${esc(b.start)} — ${esc(b.end)}</td><td>${num(b.total)}</td><td>${num(b.analyzed_success)}</td><td>${num(b.unanalyzed)}</td><td>${num(b.analyzed_risk)}</td></tr>`).join('')}</tbody></table></div><h3>原文摘选</h3><p class="b-note">报告原文为部分记录；完整匹配记录请在数据浏览中导出。</p>${(r.evidence||[]).map(v=>originalRecord(v,true)).join('')||'<p class="notice">本筛选范围未返回原文摘选。</p>'}<div class="boundaries">${(r.limits||[]).map(x=>`<p>${esc(x)}</p>`).join('')}</div><p class="b-note">生成时间：${esc(r.created_at)}</p>${reportLinks(r.id)}<p class="b-note">下载 HTML 后打开，使用浏览器打印并选择“存储为 PDF”。</p>`;
}
async function loadSchedules(){
 if(workspace.scheduleLoading)return;workspace.scheduleLoading=true;workspace.scheduleError='';renderSchedules();
 try{const result=await api('api/report-schedules');workspace.schedules=result.items||[]}
 catch(err){workspace.scheduleError=err.message}
 finally{workspace.scheduleLoading=false;renderSchedules()}
}
function renderSchedules(){
 const el=$('#schedules-list');if(!el)return;
 if(workspace.scheduleLoading){el.innerHTML='<p class="notice" role="status">正在读取周期配置…</p>';return}
 if(workspace.scheduleError){el.innerHTML=`<p class="notice warning" role="alert">${esc(workspace.scheduleError)}</p>`;return}
 if(workspace.schedules===null){el.innerHTML='<p class="notice">进入报告中心后读取配置。</p>';return}
 el.innerHTML=workspace.schedules.map(s=>{const run=s.last_run;return `<article class="schedule-card"><div class="b-panel-head"><div><h3>${esc(s.name)}</h3><p>${esc(periods[s.period]||s.period)} · ${esc(s.title)}</p></div><button class="primary-button" data-run-schedule="${esc(s.id)}" ${workspace.running?'disabled':''}>${String(workspace.running)===String(s.id)?'模拟运行中…':'模拟运行'}</button></div><p class="applied-filters">${esc(filterSummary(s.filters))}</p>${run?`<div class="run-header"><strong>最近运行：${esc({complete:'完成',partial:'部分完成',failed:'失败'}[run.status]||run.status)}</strong><span>${esc(run.finished_at||run.started_at)}</span></div><h4>四来源读取与报告日志</h4><div class="run-logs">${(run.logs||[]).map(log=>`<div class="run-log ${log.status==='failed'?'warning':''}"><span>${esc(labels[log.source]||log.source||({fetch:'来源读取',integrate:'汇总合并',filter:'条件筛选',report:'生成报告'}[log.stage]||log.stage))}</span><span>${esc({success:'成功',complete:'完成',partial:'部分完成',failed:'失败',ok:'成功'}[log.status]||log.status)}</span><span>${log.count==null?'':`${num(log.count)} ${log.stage==='report'?'份':'条'}`}</span>${log.error?`<p>${esc(log.error)}</p>`:''}</div>`).join('')}</div><h4>产出报告 · ${(run.report_ids||[]).length} 份</h4><div class="run-reports">${(run.report_ids||[]).map((id,i)=>`<div><span>周期报告 ${i+1}</span>${reportLinks(id)}</div>`).join('')||'<p class="b-note">本次运行没有产出报告。</p>'}</div>`:'<p class="notice">尚未运行。模拟运行会读取四来源历史记录，并按所选周期生成多份报告。</p>'}</article>`}).join('')||'<p class="notice">暂无自动报告配置。填写上方名称并保存周期配置。</p>';
}
async function runSchedule(id){
 if(workspace.running)return;workspace.running=id;renderSchedules();
 try{const result=await api(`api/report-schedules/${encodeURIComponent(id)}/run`,{});const s=workspace.schedules.find(s=>String(s.id)===String(id));if(s)s.last_run=result.run;workspace.scheduleError=''}
 catch(err){workspace.scheduleError=err.message}
 finally{workspace.running=null;renderSchedules()}
}
function renderTaxonomy(){
 const el=$('#taxonomy-content'),items=workspace.options.taxonomy||[];
 const groups=[...new Set(items.map(t=>t.level1).filter(Boolean))];
 el.innerHTML=`<section class="b-card"><div class="taxonomy-heading"><div><strong>${num(items.length)}</strong> 个适用标签 · ${groups.length} 个一级分类</div><input id="tag-search" type="search" placeholder="搜索分类路径" aria-label="搜索分类标签"></div><div class="taxonomy-groups"><button class="active" data-tag-group="">全部</button>${groups.map(g=>`<button data-tag-group="${esc(g)}">${esc(g)}</button>`).join('')}</div><p class="b-note">公司适用范围：通用、电动。消息分类为词面规则匹配，待人工核实。点击分类查看真实消息。</p><div id="tag-results" class="tag-results"></div></section>`;
 workspace.tagGroup='';$('#tag-search').oninput=renderTagResults;renderTagResults();
}
function renderTagResults(){
 const q=$('#tag-search').value.trim().toLowerCase(),group=workspace.tagGroup||'';
 const items=(workspace.options.taxonomy||[]).filter(t=>(!group||t.level1===group)&&valueText(t.path||[t.level1,t.level2,t.level3,t.level4].filter(Boolean).join(' / ')).toLowerCase().includes(q));
 $('#tag-results').innerHTML=items.map(t=>`<button class="tag-card" data-browse-tag="${esc(t.id)}"><span>${esc(t.level1||'')}</span><strong>${esc(t.path||[t.level1,t.level2,t.level3,t.level4].filter(Boolean).join(' / '))}</strong>${t.description?`<span class="tag-description">${esc(t.description)}</span>`:''}<small>${esc(t.department||'主责部门未提供')} · ${esc(t.domain||'领域未提供')}</small><small>查看消息 →</small></button>`).join('')||'<p class="notice">没有匹配标签。</p>';
}
async function fullMessage(id,button){
 button.disabled=true;
 try{const result=await api('api/messages/'+encodeURIComponent(id));showDialog(`<h2 id="event-title">原始消息记录</h2>${originalRecord(result.item)}`,button)}
 catch(err){let status=button.parentElement.querySelector('.message-error');if(!status){status=document.createElement('p');status.className='notice warning message-error';status.setAttribute('role','alert');button.after(status)}status.textContent=err.message}
 finally{button.disabled=false}
}
function downloadMessages(format){
 const status=$('#export-status');
 try{
  if(!['csv','json'].includes(format)||!workspace.applied||workspace.messageLoading||workspace.messageError)throw Error('请先成功应用筛选后再导出。');
  const selected=validateFilters({...workspace.applied});
  const link=document.createElement('a');link.href='api/export?'+new URLSearchParams({...selected,format});link.download=`8月筛选消息.${format}`;
  document.body.append(link);link.click();link.remove();status.textContent='已请求下载，请查看浏览器下载列表';
 }catch(err){status.textContent=err.message}
}
async function downloadFile(url,fallback,button){
 if(button.disabled)return;button.disabled=true;
 let status=$('#download-status');if(!status){status=document.createElement('p');status.id='download-status';status.className='notice';status.setAttribute('role','status');button.closest('.b-card')?.append(status)}status.textContent='正在准备完整导出…';
 try{
  const response=await fetch(url,{cache:'no-store'});if(!response.ok){let body={};try{body=await response.json()}catch{}throw Error(body.error||'导出失败，请稍后重试。')}
  const blob=await response.blob(),link=document.createElement('a'),href=URL.createObjectURL(blob);link.href=href;link.download=fallback;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),60000);status.textContent='已请求下载，请查看浏览器下载列表';
 }catch(err){status.textContent=err.message}
 finally{button.disabled=false}
}
async function load(){
 try{data=await api('api/snapshot');draw();return true}
 catch(err){if(!data)$('#app').innerHTML=`<div class="error" role="alert">${esc(err.message)} <button id="retry">重新读取</button></div>`;else $('#refresh').textContent='刷新失败，重试';$('#retry')?.addEventListener('click',()=>load());return false}
}
document.addEventListener('click',ev=>{
 const b=ev.target.closest('button');if(!b||b.disabled)return;
 if(b.dataset.event)detail(b.dataset.event);
 if(b.dataset.scroll)showPage(b.dataset.scroll);
 if(b.dataset.page)fetchMessages(Number(b.dataset.page));
 if(b.dataset.messageIndex!==undefined){const v=workspace.messages?.items[Number(b.dataset.messageIndex)];if(v)showDialog(`<h2 id="event-title">原始消息记录</h2>${originalRecord(v)}<section class="analysis-section"><h3>分析与分类状态</h3>${fieldList({'分析状态':v.analysis_status,'分析等级':v.analysis_level,'话题（词面规则待核实）':v.topic,'分类标签 ID（待核实）':v.tag_id,'分类方式':v.classification_method})}</section>`,b)}
 if(b.dataset.export&&workspace.applied)downloadMessages(b.dataset.export);
 if(b.dataset.reportExport)downloadFile(`api/reports/${encodeURIComponent(b.dataset.reportId)}/export?format=${b.dataset.reportExport}`,`历史周期报告-${b.dataset.reportId}.${b.dataset.reportExport}`,b);
 if(b.dataset.fullMessage)fullMessage(b.dataset.fullMessage,b);
 if(b.dataset.runSchedule)runSchedule(b.dataset.runSchedule);
 if(b.dataset.tagGroup!==undefined){workspace.tagGroup=b.dataset.tagGroup;document.querySelectorAll('[data-tag-group]').forEach(x=>x.classList.toggle('active',x===b));renderTagResults()}
 if(b.dataset.browseTag){browseFilters={...initialFilters,...workspace.options.range,tag_id:b.dataset.browseTag};showPage('browse');fetchMessages(1)}
 switch(b.dataset.action){
  case 'options-retry':loadOptions();break;
  case 'messages-retry':fetchMessages(workspace.messagePage);break;
  case 'browse-reset':browseFilters={...initialFilters,...workspace.options.range};fetchMessages(1);break;
  case 'to-report':reportFilters={...workspace.applied};renderReports();showPage('reports');break;
  case 'save-schedule':submitReport(true);break;
  case 'schedules-refresh':loadSchedules();break;
 }
});
function closeDetail(){if(submitting)return;$('#details').close();if(activeEvent instanceof HTMLElement)activeEvent.focus();else Array.from(document.querySelectorAll('[data-event]')).find(b=>b.dataset.event===activeEvent)?.focus()}
$('#close').onclick=closeDetail;
$('#details').addEventListener('cancel',ev=>{ev.preventDefault();closeDetail()});
Promise.allSettled([load(),loadOptions()]);
