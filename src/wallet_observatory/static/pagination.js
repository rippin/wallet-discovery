'use strict';
// Paginate the loaded snapshot locally; controls never trigger collection or RPC.
const listPages=new Map();
const listViews=new Map();
function paginateLists(root,scope,reset=false){
  root.querySelectorAll('.pagination').forEach(el=>el.remove());
  for(const [key,view] of listViews)if(!view.container.isConnected)listViews.delete(key);
  const tables=[...root.querySelectorAll('table')].map(table=>({container:table.tBodies[0],anchor:table.closest('.table-wrap')||table,rows:[...table.tBodies[0].rows],size:10}));
  const parents=[...new Set([...root.querySelectorAll('.feed-item')].map(el=>el.parentElement))];
  const feeds=parents.map(container=>({container,anchor:container,rows:[...container.children].filter(el=>el.classList.contains('feed-item')),size:5,feed:true}));
  [...tables,...feeds].forEach((view,index)=>{
    const key=scope+':'+index;
    if(reset)listPages.delete(key);
    const saved=listPages.get(key)||{page:0,size:view.size};
    view.key=key;view.state=saved;view.controls=[];
    for(const where of ['top','bottom']){
      const controls=document.createElement('div');controls.className='pagination';
      controls.setAttribute('role','group');controls.setAttribute('aria-label','List pagination');
      if(view.feed){if(where==='top')view.rows[0]?.before(controls);else view.rows.at(-1)?.after(controls)}
      else if(where==='top')view.anchor.before(controls);else view.anchor.after(controls);
      view.controls.push(controls);
    }
    listViews.set(key,view);drawListPage(view);
  });
}
function drawListPage(view){
  const {state,rows,key}=view;
  const count=Math.max(1,Math.ceil(rows.length/state.size));
  state.page=Math.max(0,Math.min(state.page,count-1));listPages.set(key,state);
  rows.forEach((row,index)=>{row.hidden=index<state.page*state.size||index>=(state.page+1)*state.size});
  const from=rows.length?state.page*state.size+1:0,to=Math.min(rows.length,(state.page+1)*state.size);
  const safeKey=key.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  view.controls.forEach(el=>{
    el.innerHTML=`<span>${from}–${to} of ${rows.length} loaded · Page ${state.page+1} of ${count}</span><label>Per page <select data-list-size="${safeKey}" aria-label="Items per page">${[5,10,25,50].map(n=>`<option value="${n}" ${n===state.size?'selected':''}>${n}</option>`).join('')}</select></label><button class="tiny-button" data-list-key="${safeKey}" data-list-step="-1" ${state.page===0?'disabled':''}>Previous</button><button class="tiny-button" data-list-key="${safeKey}" data-list-step="1" ${state.page===count-1?'disabled':''}>Next</button>`;
  });
}
document.addEventListener('click',e=>{
  const button=e.target.closest('button[data-list-key]');if(!button||button.disabled)return;
  const view=listViews.get(button.dataset.listKey);if(!view)return;
  view.state.page+=Number(button.dataset.listStep);drawListPage(view);
});
document.addEventListener('change',e=>{
  const select=e.target.closest('select[data-list-size]');if(!select)return;
  const view=listViews.get(select.dataset.listSize);if(!view)return;
  const size=Number(select.value);if(![5,10,25,50].includes(size))return;
  view.state.size=size;view.state.page=0;drawListPage(view);
});
