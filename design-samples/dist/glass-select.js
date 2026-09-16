/* Shared styled single-select menus. Native fields remain the form authority. */
(()=>{
 const fields=new WeakMap();let opened=null,serial=0;
 function close(focus=false){if(!opened)return;const a=opened;opened=null;a.menu.remove();a.button.setAttribute('aria-expanded','false');a.button.removeAttribute('aria-activedescendant');if(focus&&a.button.isConnected)a.button.focus()}
 function enhance(select){
  if(fields.has(select)||select.multiple||select.size>1)return;
  const wrapper=document.createElement('span');wrapper.className='glass-select';
  select.before(wrapper);wrapper.append(select);select.classList.add('gs-native');select.hidden=true;select.tabIndex=-1;select.setAttribute('aria-hidden','true');
  const button=document.createElement('button');button.type='button';button.className='glass-select-trigger';button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');
  const label=select.getAttribute('aria-label')||select.labels?.[0]?.textContent.split('\n')[0]?.trim()||select.name||'选择选项';
  button.setAttribute('aria-label',label.replace(Array.from(select.options).map(o=>o.textContent).join(''),'').trim()||'选择选项');
  const id='glass-menu-'+(++serial);button.setAttribute('aria-controls',id);wrapper.append(button);fields.set(select,button);
  function sync(){button.textContent=select.selectedOptions[0]?.textContent||'请选择';button.disabled=select.disabled;if(opened?.select===select)close()}
  function open(){
   if(select.disabled)return;close();const options=Array.from(select.options),menu=document.createElement('div');menu.className='glass-select-menu';menu.id=id;menu.setAttribute('role','listbox');menu.setAttribute('aria-label',button.getAttribute('aria-label'));
   const parent=select.closest('dialog[open]')||document.body;parent.append(menu);
   if(menu.showPopover){menu.setAttribute('popover','manual');menu.showPopover()}
   let index=Math.max(0,select.selectedIndex);
   const items=options.map((o,i)=>{const item=document.createElement('div');item.id=id+'-'+i;item.setAttribute('role','option');item.setAttribute('aria-selected',String(o.selected));item.setAttribute('aria-disabled',String(o.disabled));item.textContent=o.textContent;item.addEventListener('pointerdown',e=>e.preventDefault());item.onclick=()=>choose(i);menu.append(item);return item});
   function choose(i){if(options[i].disabled)return;select.value=options[i].value;close(true);sync();select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}))}
   function highlight(i){index=i;items.forEach((el,n)=>el.classList.toggle('active',n===i));button.setAttribute('aria-activedescendant',items[i]?.id||'');const item=items[i];if(item){if(item.offsetTop<menu.scrollTop)menu.scrollTop=item.offsetTop;else if(item.offsetTop+item.offsetHeight>menu.scrollTop+menu.clientHeight)menu.scrollTop=item.offsetTop+item.offsetHeight-menu.clientHeight}}
   function move(direction){let next=index;for(let n=0;n<items.length;n++){next=(next+direction+items.length)%items.length;if(!options[next].disabled)break}highlight(next)}
   const r=button.getBoundingClientRect(),width=Math.min(Math.max(r.width,180),innerWidth-24),bottom=innerHeight-r.bottom-12,top=r.top-12;
   const available=Math.max(80,Math.min(280,Math.max(bottom,top)));menu.style.width=width+'px';menu.style.maxHeight=available+'px';menu.style.left=Math.max(12,Math.min(r.left,innerWidth-width-12))+'px';
   if(bottom>=Math.min(menu.scrollHeight,280)||bottom>=top)menu.style.top=(r.bottom+6)+'px';else menu.style.bottom=(innerHeight-r.top+6)+'px';
   opened={select,button,menu,move,choose:()=>choose(index),highlight,items};button.setAttribute('aria-expanded','true');highlight(index);
  }
  button.onclick=()=>opened?.select===select?close():open();
  button.onkeydown=e=>{if(['ArrowDown','ArrowUp','Enter',' ','Escape','Home','End','Tab'].includes(e.key)){
   if(e.key==='Tab'){close();return}e.preventDefault();
   if(e.key==='Escape'){close(true);return}
   if(opened?.select!==select){open();return}
   if(e.key==='ArrowDown'||e.key==='ArrowUp')opened.move(e.key==='ArrowDown'?1:-1);
   else if(e.key==='Home')opened.highlight(0);else if(e.key==='End')opened.highlight(opened.items.length-1);else opened.choose();
  }};
  select.addEventListener('input',sync);select.addEventListener('change',sync);select.addEventListener('invalid',e=>{e.preventDefault();button.focus();open()});sync();
 }
 const observer=new MutationObserver(()=>{if(opened&&!opened.button.isConnected)close();document.querySelectorAll('select').forEach(enhance)});
 observer.observe(document.body,{childList:true,subtree:true});document.querySelectorAll('select').forEach(enhance);
 document.addEventListener('pointerdown',e=>{if(opened&&!opened.menu.contains(e.target)&&!opened.button.contains(e.target))close()},true);
 for(const type of ['wheel','touchmove'])document.addEventListener(type,e=>{if(opened&&!opened.menu.contains(e.target))close()},{capture:true,passive:true});window.addEventListener('resize',()=>close());
})();
