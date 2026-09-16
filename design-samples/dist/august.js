let data=null, activeEvent=null, submitting=false;
const filters={query:'',source:'',status:'',level:''};
let glassLevel=52;
const icons={overview:'▦',events:'◇',coverage:'▤',history:'◷'};

const labels={wecom:'企微社群',wechat_export:'民间微信群＊',voc:'公域 VOC',suggestions:'意见建议'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number(n||0).toLocaleString('zh-CN');
function review(e){return data.reviews?.[e.id]||{decision:'pending',level:e.level||''}}
function stateLabel(e){return {pending:'待核验',confirmed:'已确认',rejected:'已驳回'}[review(e).decision]}
let riskPage=1,riskResult=null,riskRequest=0;
function draw(){
 const m=data.metrics||{},daily=data.daily||[],max=Math.max(1,...daily.map(x=>x.count));
 $('#app').innerHTML=`<section class="blue-v2"><aside class="b-sidebar"><a href="#" class="b-brand"><span class="b-logo">9</span>ninebot<span class="brand-dot">.</span><span class="b-brand-sub">舆情洞察工作空间</span></a><div class="nav-caption">WORKSPACE</div><nav aria-label="工作空间">${[['overview','▦','总览'],['events','◇','风险候选与证据'],['history','◷','核验记录'],['browse','▤','数据浏览'],['reports','▧','报告中心']].map(([id,icon,name])=>`<button class="b-nav" data-scroll="${id}"><span class="nav-icon">${icon}</span>${name}</button>`).join('')}</nav><div class="sidebar-poem"><span class="small-orb"></span><h3>每一种声音，<br>都值得被听见。</h3><p>连接用户反馈<br>让关切得到回应</p></div><div class="glass-control"><label for="glass-level">玻璃透明度</label><input id="glass-level" type="range" min="25" max="85" value="${glassLevel}"></div><div class="b-sidebar-bottom">8月模拟运行 · 通知仅模拟</div></aside><div class="b-main"><header class="b-toolbar"><span>九号电动 / 舆情洞察</span><span class="b-account">模拟时钟 <b id="sim-now">${esc(data.clock.now.replace('T',' ').slice(0,19))}</b></span></header><div class="b-content"><section class="clock-controls b-card"><span id="clock-state">${data.clock.speed===0?'已暂停':`${data.clock.speed}× 推进`}</span><button data-clock="${data.clock.speed===0?'resume':'pause'}">${data.clock.speed===0?'继续':'暂停'}</button><button data-clock="advance" data-seconds="3600">快进 1 小时</button><button data-clock="advance" data-seconds="86400">快进 1 天</button><select id="clock-speed" aria-label="模拟时间速度">${[[1,'正常速度'],[60,'1秒 = 1分钟'],[3600,'1秒 = 1小时']].map(([v,n])=>`<option value="${v}" ${data.clock.speed===v?'selected':''}>${n}</option>`).join('')}</select><button data-clock="reset">重置至 8月15日 11:00</button><span id="clock-error" role="status"></span></section><div id="overview-pane"><section class="b-hero"><div class="b-hero-copy"><span class="b-kicker">THE VOICE BEHIND EVERY RIDE</span><h1>听见每一程，<br><span>洞察每一种声音。</span></h1><p>在每一天的用户原声中，<br>发现需要回应的关切。</p><button class="b-dark-button" data-scroll="events">查看风险候选 →</button></div><div class="hero-art" aria-hidden="true"><div class="glass-orb"></div><div class="glass-orbit"></div><span class="floating-tag">✧ CONNECTING VOICES</span></div></section><div class="section-title"><h2>过去 24 小时 · 用户原声</h2><span class="b-tag">按模拟时刻滚动更新</span></div><section class="sources-section"><div class="actual-sources">${data.sources.map(s=>`<div class="actual-source"><i class="source-dot ${s.source}"></i><strong>${esc(labels[s.source])}</strong><span>${num(s.count)}</span><small>条</small></div>`).join('')}</div></section><div class="b-metrics">${[['客户原声',m.voices24,'过去24小时 · 四渠道合计'],['模型保留风险项',m.risks24,'过去24小时 · R1–R3原声'],['触发预警内容',m.alerts24,'过去24小时 · R1/R2'],['触发预警内容',m.alerts7,'过去7天 · R1/R2']].map(([name,n,note])=>`<section class="b-card b-stat"><span>${name}</span><strong>${num(n)}</strong><small>${note}</small></section>`).join('')}</div><section class="b-card"><div class="b-panel-head"><h2>每日风险项 · 过去 7 天</h2><span class="b-tag">每柱24小时</span></div><div class="daily-bars replay-bars">${daily.map(d=>`<div class="replay-day"><span>${num(d.count)}</span><div class="day-bar" style="height:${Math.max(2,d.count/max*140)}px" title="${esc(d.start)} 至 ${esc(d.end)}：${d.count}条"></div><small>${d.label}</small></div>`).join('')}</div><p class="b-note">风险项按成功分析的 R1–R3 原声去重计数；R1/R2 在消息进入模拟系统时触发模拟预警，不代表已人工确认或已发送通知。未分析原声不计为已排除风险。</p></section></div><section id="events" class="workspace-pane" hidden><div class="workspace-heading"><div><span class="b-kicker">RISK & EVIDENCE</span><h1>风险候选与证据</h1><p>截至当前模拟时刻 · 按消息时间倒序 · 每页20条</p></div></div><section class="b-card"><div class="actual-tools"><input id="search" value="${esc(filters.query)}" placeholder="搜索主题、车型、问题" aria-label="搜索风险候选"><select id="filter" aria-label="按来源筛选"><option value="">全部来源</option>${Object.entries(labels).map(([k,v])=>`<option value="${k}" ${filters.source===k?'selected':''}>${esc(v)}</option>`).join('')}</select><select id="level-filter" aria-label="按风险等级筛选">${[['','全部风险等级'],...['R1','R2','R3','R4'].map(x=>[x,x])].map(([k,v])=>`<option value="${k}" ${filters.level===k?'selected':''}>${v}</option>`).join('')}</select><select id="status-filter" aria-label="按核验状态筛选">${[['','全部状态'],['pending','待核验'],['confirmed','已确认'],['rejected','已驳回']].map(([k,v])=>`<option value="${k}" ${filters.status===k?'selected':''}>${v}</option>`).join('')}</select></div><div class="b-table-wrap"><table><thead><tr><th>问题与车型</th><th>时间 / 来源</th><th>等级</th><th>核验状态</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table></div><p id="empty" hidden>没有匹配的风险候选。</p><div id="risk-pagination" class="pagination"></div></section></section><section id="history" class="workspace-pane b-card" hidden><h1>核验记录</h1>${data.history.length?data.history.map(r=>`<div class="review-row">${esc(r.level)} · ${r.decision==='confirmed'?'确认':'驳回'}<small>${esc(r.note)}</small><small>${esc(r.updated_at)}</small></div>`).join(''):'<p>当前模拟时刻尚无核验记录。</p>'}</section><section id="browse" class="workspace-pane" hidden><div class="workspace-heading"><h1>数据浏览</h1><p>仅展示模拟时刻之前的真实消息</p></div><div id="browse-content"></div></section><section id="reports" class="workspace-pane" hidden><div class="workspace-heading"><h1>报告中心</h1><p>基于当前模拟时刻已进入系统的原声生成报告</p></div><div id="reports-content"></div></section><footer class="b-footer">历史数据模拟 · Asia/Shanghai · 原始记录时间模拟抓取时间</footer></div></div></section>`;
 for(const [id,key] of [['search','query'],['filter','source'],['status-filter','status'],['level-filter','level']])$('#'+id).oninput=()=>{filters[key]=$('#'+id).value;riskPage=1;loadRisks()};
 $('#glass-level').oninput=e=>{glassLevel=Number(e.target.value);document.documentElement.style.setProperty('--glass-alpha',glassLevel/100)};
 $('#clock-speed').onchange=e=>changeClock({action:'speed',speed:Number(e.target.value)});
 renderWorkspace();showPage(workspace.page,false);
}
async function loadRisks(){
 const req=++riskRequest;$('#rows').innerHTML='<tr><td colspan="5">正在读取风险原声…</td></tr>';
 try{const r=await api('api/risks?'+new URLSearchParams({page:riskPage,source:filters.source,status:filters.status,level:filters.level,q:filters.query}));if(req!==riskRequest)return;riskResult=r;riskPage=r.page;data.events=r.items;data.reviews=r.reviews;rows()}
 catch(e){if(req===riskRequest)$('#rows').innerHTML=`<tr><td colspan="5">${esc(e.message)}</td></tr>`}
}
async function changeClock(change){
 try{await api('api/clock',change);workspace.messages=null;workspace.applied=null;workspace.report=null;riskResult=null;riskPage=1;topicStudio.loaded=false;await load();await loadOptions();if(workspace.page==='events')await loadRisks();if(workspace.page==='browse')await fetchMessages(1)}catch(e){$('#clock-error').textContent=e.message}
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
 $('#rows').innerHTML=events.map(e=>{const r=review(e);return `<tr><td>${esc(e.issue||'待分析线索')}<small>${esc(e.vehicle||'')} ${esc(e.topic||'')}</small>${isUnanalysed(e)?'<small class="rule-note">规则线索 · 非模型结论</small>':''}</td><td>${esc(e.day)}<small>${esc(labels[e.source]||e.source)}</small></td><td>${isUnanalysed(e)?'<span class="state-pill">待分析线索</span>':`<span class="b-pill ${r.level==='R1'?'red':'amber'}">${esc(r.level||'未提供')}</span>`}${isUnanalysed(e)&&r.decision!=='pending'?`<small>人工核验：${esc(r.level)}</small>`:''}</td><td><span class="state-pill ${esc(r.decision)}">${esc(stateLabel(e)||r.decision)}</span></td><td><button class="b-link" data-event="${esc(e.id)}">查看原文 →</button></td></tr>`}).join('');
 $('#empty').hidden=events.length>0;
 if(riskResult)$('#risk-pagination').innerHTML=`<button data-risk-page="${riskPage-1}" ${riskPage<=1?'disabled':''}>上一页</button><span>第 ${riskPage} / ${riskResult.pages} 页 · ${num(riskResult.total)} 条 · 每页20条</span><button data-risk-page="${riskPage+1}" ${riskPage>=riskResult.pages?'disabled':''}>下一页</button>`;
}
function originalRecord(v,excerpt=false){
 const available=v.original_available!==false&&v.raw_text!=null;
 return `<article class="original-record"><div class="evidence-meta">${esc(v.time||'时间未提供')} · ${esc(v.source_name||labels[v.source]||'来源未提供')}</div>${fieldList({'真实群名':v.group_name,'渠道':v.channel,'平台':v.platform})}<h3>${!available?'原始正文未提供':excerpt?'原文摘录（最多500字）':'完整原文'}</h3>${available?`<blockquote>${esc(v.raw_text)}</blockquote>`:'<p class="notice warning">接口未提供原始正文，请核对原始记录。</p>'}${v.original_available!==false&&v.raw_quote?`<h3>${excerpt?'原始引用摘录（最多500字）':'原始引用'}</h3><blockquote>${esc(v.raw_quote)}</blockquote>`:''}<details><summary>原始记录字段</summary>${fieldList({'记录 ID':v.message_id??v.id,'来源名称':v.source_name,'作者':v.author,'原生 ID':v.native_id,'来源文件':v.source_file,'来源行':v.source_row})}${fieldList(v.raw_fields||v.raw_json||{})}</details>${excerpt?`<button class="b-link" data-full-message="${esc(v.message_id??v.id)}">读取原始记录 →</button>`:''}</article>`;
}
function showDialog(html,opener){activeEvent=opener;$('#detail-content').innerHTML=html;if(!$('#details').open)$('#details').showModal()}
function detail(id){
 const e=data.events.find(x=>x.id===id);if(!e)return;
 const r=review(e),unanalysed=isUnanalysed(e);
 showDialog(`<span class="b-kicker">${esc(labels[e.source]||e.source)} / ${esc(e.day)}</span><h2 id="event-title">${esc(e.issue||'待分析线索')} ${esc(e.vehicle||'')}</h2>${unanalysed?'<p class="notice">待分析线索 · 规则筛选，尚无模型结论。</p>':''}<section class="original-section"><h3>真实来源与原文 · ${(e.evidence||[]).length} 条记录</h3>${(e.evidence||[]).map(v=>originalRecord(v)).join('')||'<p class="notice">未返回原始证据记录。</p>'}</section><section class="analysis-section"><h3>${unanalysed?'分析状态':'模型判断'}</h3>${unanalysed?'<p>尚未进行模型分析。人工核验时请依据上方原始记录。</p>':`<p>${esc(e.summary||'模型摘要未提供')}</p>${(e.evidence||[]).map(v=>`<div class="analysis-record">${fieldList({'意图':v.intent,...(v.confidence==null?{}:{'模型自评置信度':v.confidence}),'判断依据':v.reason})}<details><summary>模型分析时的上下文（预处理）</summary><blockquote>${esc(v.text||'未提供')}</blockquote>${v.quote_text?`<blockquote>${esc(v.quote_text)}</blockquote>`:''}<pre>${esc(typeof v.context_json==='string'?v.context_json:JSON.stringify(v.context_json||{},null,2))}</pre></details></div>`).join('')}`}</section><form class="review-form" id="review-form"><h3>人工核验</h3><label>最终等级 <select name="level" required><option value="">请选择等级</option>${['R1','R2','R3','R4'].map(x=>`<option value="${x}" ${(!unanalysed||r.decision!=='pending')&&r.level===x?'selected':''}>${x}</option>`).join('')}</select></label><label class="note-label" for="review-note">核验依据</label><textarea id="review-note" name="note" maxlength="1000" required placeholder="依据真实原文填写判断依据或驳回原因">${esc(r.note||'')}</textarea><div class="actions"><button value="confirmed">确认候选</button><button value="rejected" class="reject">驳回候选</button></div><p class="review-status" id="review-status" role="status"></p></form>`,id);
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
 return `<div class="filter-grid"><label>开始日期<input type="date" name="start" value="${esc(f.start)}" min="${esc(o.range?.start||'')}" max="${esc(o.range?.end||'')}" required></label><label>结束日期<input type="date" name="end" value="${esc(f.end)}" min="${esc(o.range?.start||'')}" max="${esc(o.range?.end||'')}" required></label><label>消息来源<select name="source"><option value="">全部来源</option>${selectedOptions(o.sources,f.source)}</select></label><label>渠道<select name="channel"><option value="">全部渠道</option>${selectedOptions(o.channels,f.channel)}</select></label><label>话题<select name="topic"><option value="">全部话题</option>${selectedOptions(o.topics,f.topic)}</select></label><label class="query-field">关键词<input name="q" value="${esc(f.q)}" placeholder="搜索真实原文" type="search"></label></div>`;
}
function readFilters(form){const f=Object.fromEntries(new FormData(form));return Object.fromEntries(Object.keys(initialFilters).map(k=>[k,String(f[k]||'').trim()]))}
function validateFilters(f){if(!f.start||!f.end||f.start>f.end)throw Error('请选择有效时间范围，结束日期不能早于开始日期。');return f}
function filterSummary(f){return [f.start+' — '+f.end,f.source?labels[f.source]||f.source:'全部来源',f.channel||'全部渠道',f.topic||'全部话题',f.q?`关键词：${f.q}`:''].filter(Boolean).join(' · ')}
function showPage(page,scroll=true){
 workspace.page=page;
 $('#overview-pane').hidden=page!=='overview';for(const id of ['events','history','browse','reports'])$('#'+id).hidden=id!==page;
 document.querySelectorAll('.b-nav').forEach(b=>b.classList.toggle('active',b.dataset.scroll===page));
 if(scroll)window.scrollTo({top:0,behavior:'smooth'});
 if(page==='events')loadRisks();
 if(page==='browse'&&workspace.options&&!workspace.messages&&!workspace.messageLoading)fetchMessages(1);
 if(page==='reports'&&workspace.options){loadSchedules();renderTopicStudio()}
}
function renderWorkspace(){
 for(const id of ['browse','reports'])if(!workspace.options)$('#'+id+'-content').innerHTML='<p>正在读取筛选选项…</p>';
 if(!workspace.options)return;renderBrowse();renderReports();
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
 catch(err){if(!data)$('#app').innerHTML=`<div class="error" role="alert">${esc(err.message)} <button id="retry">重新读取</button></div>`;else console.warn('刷新失败');$('#retry')?.addEventListener('click',()=>load());return false}
}
document.addEventListener('click',ev=>{
 const b=ev.target.closest('button');if(!b||b.disabled)return;
 if(b.dataset.event)detail(b.dataset.event);
 if(b.dataset.scroll)showPage(b.dataset.scroll);
 if(b.dataset.riskPage){riskPage=Number(b.dataset.riskPage);loadRisks()}
 if(b.dataset.clock)changeClock({action:b.dataset.clock,seconds:Number(b.dataset.seconds)});
 if(b.dataset.page)fetchMessages(Number(b.dataset.page));
 if(b.dataset.messageIndex!==undefined){const v=workspace.messages?.items[Number(b.dataset.messageIndex)];if(v)showDialog(`<h2 id="event-title">原始消息记录</h2>${originalRecord(v)}<section class="analysis-section"><h3>分析与分类状态</h3>${fieldList({'分析状态':v.analysis_status,'分析等级':v.analysis_level,'话题（词面规则待核实）':v.topic})}</section>`,b)}
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

setInterval(async()=>{if(!data||document.hidden||$('#details').open)return;try{const fresh=await api('api/snapshot');if(workspace.page==='overview'){data=fresh;draw()}else{data.clock=fresh.clock;$('#sim-now').textContent=fresh.clock.now.replace('T',' ').slice(0,19);if(workspace.page==='events')loadRisks()}}catch{}},10000);
