const $=s=>document.querySelector(s);
let graph=null;
let selectedNode=null;

const esc=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const domainLabels={natural_hazards:'Risques naturels',weather_climate:'Climat & météo',cyber_technology:'Technologie & cyber',public_health:'Santé publique',financial_stress:'Stress financier',energy:'Énergie',economy_labor:'Économie & emploi',supply_fuel:'Approvisionnement',social_collective_behavior:'Comportements collectifs',geopolitics_security:'Géopolitique & sécurité',regulation_policy:'Régulation & politiques',transport_mobility:'Transport & mobilité'};
function hash(str){let h=2166136261;for(const c of String(str)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return h>>>0}
function fmt(n){return new Intl.NumberFormat('fr-FR').format(Number(n)||0)}
function nodeClass(n){return n.type==='source'?'node-source':n.type==='forecast'?'node-forecast':'node-concept'}
function edgeClass(e){return e.type==='structural_prior'?'edge-line structural':e.type==='evidence_support'?'edge-line evidence':'edge-line'}

async function loadGraph(){
  const res=await fetch('/api/causal-graph',{cache:'no-store'});
  if(!res.ok) throw new Error(`HTTP ${res.status}`);
  graph=await res.json();
  $('#causalStatus').textContent=`Graphe · ${new Date(graph.generated_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
  renderMetrics(); populateControls(); renderLeverage(); renderGraph();
}

function renderMetrics(){
  const m=graph.metrics||{};
  const values=[m.nodes,m.edges,m.forecast_nodes,m.evidence_backed_edges];
  [...document.querySelectorAll('#causalMetrics strong')].forEach((el,i)=>el.textContent=fmt(values[i]));
}

function populateControls(){
  const domains=[...new Set((graph.nodes||[]).filter(n=>n.type==='forecast'&&n.domain).map(n=>n.domain))].sort();
  $('#domainFilter').innerHTML='<option value="">Tous les domaines</option>'+domains.map(d=>`<option value="${esc(d)}">${esc(domainLabels[d]||d)}</option>`).join('');
  const leverage=graph.metrics?.top_leverage||[];
  const domainOpts=domains.map(d=>`<option value="domain:${esc(d)}">DOMAINE · ${esc(domainLabels[d]||d)}</option>`).join('');
  const nodeOpts=leverage.map(n=>`<option value="${esc(n.node_id)}">${n.type==='forecast'?'SCÉNARIO':'MÉCANISME'} · ${esc(n.label.slice(0,90))}</option>`).join('');
  $('#scenarioTarget').innerHTML='<option value="">Choisir un point de levier…</option>'+domainOpts+nodeOpts;
}

function renderLeverage(){
  const rows=graph.metrics?.top_leverage||[];
  $('#leverageList').innerHTML=rows.length?rows.slice(0,10).map((x,i)=>`<div class="leverage-item" data-node="${esc(x.node_id)}"><div><strong>${String(i+1).padStart(2,'0')} · ${esc(x.label)}</strong><span>${esc(x.type==='forecast'?(domainLabels[x.domain]||x.domain||'Scénario'):'Mécanisme')} · ${x.downstream_nodes} nœuds en aval</span></div><span class="leverage-score">${Number(x.leverage_score).toFixed(2)}</span></div>`).join(''):'<div class="causal-empty">Aucun point de levier disponible.</div>';
  document.querySelectorAll('.leverage-item').forEach(el=>el.addEventListener('click',()=>inspectNode(el.dataset.node,true)));
}

function visibleSet(){
  const domain=$('#domainFilter').value;
  const q=$('#graphSearch').value.trim().toLowerCase();
  const nodes=graph.nodes||[],edges=graph.edges||[];
  let ids=new Set(nodes.filter(n=>(!domain||n.domain===domain||n.type==='source')&&(!q||String(n.label).toLowerCase().includes(q))).map(n=>n.id));
  if(q){
    const expanded=new Set(ids);
    for(const e of edges) if(ids.has(e.from)||ids.has(e.to)){expanded.add(e.from);expanded.add(e.to)}
    ids=expanded;
  }
  if(domain){
    const expanded=new Set(ids);
    for(const e of edges) if(ids.has(e.from)||ids.has(e.to)){expanded.add(e.from);expanded.add(e.to)}
    ids=expanded;
  }
  const leverageIds=new Set((graph.metrics?.top_leverage||[]).map(x=>x.node_id));
  const ordered=nodes.filter(n=>ids.has(n.id)).sort((a,b)=>{
    const pa=(a.type==='forecast'?3:a.type==='source'?2:leverageIds.has(a.id)?2:1);
    const pb=(b.type==='forecast'?3:b.type==='source'?2:leverageIds.has(b.id)?2:1);
    return pb-pa;
  }).slice(0,150);
  return new Set(ordered.map(n=>n.id));
}

function positionNode(n,domains){
  const H=620,W=1200,padY=55;
  if(n.type==='source'){
    const sourceNodes=(graph.nodes||[]).filter(x=>x.type==='source');
    const idx=Math.max(0,sourceNodes.findIndex(x=>x.id===n.id));
    return {x:58,y:padY+(idx+1)*(H-padY*2)/(sourceNodes.length+1)};
  }
  const domain=n.domain||'unknown';
  const di=Math.max(0,domains.indexOf(domain));
  const rowY=padY+(di+.5)*(H-padY*2)/Math.max(1,domains.length);
  const jitter=((hash(n.id)%1000)/1000-.5)*Math.min(42,(H-padY*2)/Math.max(4,domains.length)*.55);
  if(n.type==='forecast') return {x:780+(Number(n.horizon_order||0))*78,y:rowY+jitter};
  return {x:255+(hash(n.id)%420),y:rowY+jitter};
}

function renderGraph(){
  if(!graph) return;
  const svg=$('#causalGraph'),ids=visibleSet();
  const nodes=(graph.nodes||[]).filter(n=>ids.has(n.id));
  const edges=(graph.edges||[]).filter(e=>ids.has(e.from)&&ids.has(e.to));
  const domains=[...new Set(nodes.filter(n=>n.type!=='source'&&n.domain).map(n=>n.domain))];
  const pos=new Map(nodes.map(n=>[n.id,positionNode(n,domains)]));
  const lines=edges.slice(0,320).map(e=>{const a=pos.get(e.from),b=pos.get(e.to);if(!a||!b)return'';return `<line class="${edgeClass(e)}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"><title>${esc(e.rationale||e.type)}</title></line>`}).join('');
  const circles=nodes.map(n=>{const p=pos.get(n.id);const r=n.type==='forecast'?7:n.type==='source'?5:5.5;const label=n.type==='forecast'?String(n.label).slice(0,34):'';return `<g data-node-group="${esc(n.id)}"><circle class="node-circle ${nodeClass(n)}" data-node="${esc(n.id)}" cx="${p.x}" cy="${p.y}" r="${r}"><title>${esc(n.label)}</title></circle>${label?`<text class="node-label" x="${p.x+10}" y="${p.y+3}">${esc(label)}</text>`:''}</g>`}).join('');
  svg.setAttribute('viewBox','0 0 1200 620');
  svg.innerHTML=`<g class="edges">${lines}</g><g class="nodes">${circles}</g>`;
  $('#graphEmpty').hidden=nodes.length>0;
  svg.querySelectorAll('[data-node]').forEach(el=>el.addEventListener('click',()=>inspectNode(el.dataset.node,false)));
  if(selectedNode&&ids.has(selectedNode)) highlight(selectedNode);
}

function inspectNode(id,setTarget){
  selectedNode=id;
  const n=(graph.nodes||[]).find(x=>x.id===id);if(!n)return;
  const inEdges=(graph.edges||[]).filter(e=>e.to===id),outEdges=(graph.edges||[]).filter(e=>e.from===id);
  const kind=n.type==='forecast'?'Scénario prédictif':n.type==='source'?'Source observée':'Mécanisme causal hypothétique';
  const detail=n.type==='forecast'?`${n.probability_percent}% · ${domainLabels[n.domain]||n.domain} · ${n.horizon_tier||'horizon non défini'}`:`${inEdges.length} liens entrants · ${outEdges.length} liens sortants`;
  $('#nodeInspector').innerHTML=`<small>${esc(kind.toUpperCase())}</small><strong>${esc(n.label)}</strong><p>${esc(detail)}. ${n.type==='forecast'?'La probabilité affichée reste celle du moteur public, pas celle d’une simulation.':'Les arêtes structurelles sont des hypothèses et restent distinguées des preuves observées.'}</p>`;
  if(setTarget){const opt=[...$('#scenarioTarget').options].find(o=>o.value===id);if(opt)$('#scenarioTarget').value=id;}
  highlight(id);
}

function highlight(id){
  const svg=$('#causalGraph');
  const neighbors=new Set([id]);
  for(const e of graph.edges||[]) if(e.from===id||e.to===id){neighbors.add(e.from);neighbors.add(e.to)}
  svg.querySelectorAll('[data-node-group]').forEach(g=>g.classList.toggle('graph-dim',!neighbors.has(g.dataset.nodeGroup)));
  svg.querySelectorAll('.edge-line').forEach(e=>e.classList.toggle('graph-dim',e.dataset.from!==id&&e.dataset.to!==id));
}

function resetGraph(){selectedNode=null;$('#domainFilter').value='';$('#graphSearch').value='';renderGraph();$('#nodeInspector').innerHTML='<small>SÉLECTION</small><strong>Cliquez sur un nœud</strong><p>Le graphe affichera ici son type, sa portée et ses principaux liens.</p>'}

async function runScenario(ev){
  ev.preventDefault();
  const target=$('#scenarioTarget').value;if(!target)return;
  const button=$('.scenario-run');button.disabled=true;button.textContent='Propagation…';
  try{
    const res=await fetch('/api/scenario-lab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interventions:[{target,direction:$('#scenarioDirection').value,strength:Number($('#scenarioStrength').value)}],max_hops:Number($('#scenarioHops').value)})});
    const data=await res.json();if(!res.ok)throw new Error(data.error||`HTTP ${res.status}`);
    renderScenario(data);
  }catch(err){$('#scenarioSummary').innerHTML=`<p>Simulation indisponible : ${esc(err.message)}</p>`;$('#scenarioResults').innerHTML='<div class="causal-empty">Aucun résultat.</div>'}
  finally{button.disabled=false;button.innerHTML='Propager le scénario <span>→</span>'}
}

function renderScenario(data){
  const s=data.summary||{};
  $('#scenarioSummary').innerHTML=`<p><strong>${fmt(s.affected)} scénarios affectés</strong> · ${fmt(s.second_order_effects)} effets de second ordre · déplacement maximal ${fmt(s.max_absolute_delta_points)} points. Les valeurs simulées restent hors Track Record.</p>`;
  $('#resultMeta').textContent=`${data.max_hops} niveaux · ${data.mode}`;
  const rows=data.affected_forecasts||[];
  $('#scenarioResults').innerHTML=rows.length?rows.slice(0,16).map(x=>{
    const up=x.delta_points>=0;const path=x.paths?.[0];
    const pathText=path?.path?.map(p=>p.label).join(' → ')||'Intervention directe';
    return `<article class="result-card"><header><h3>${esc(x.title)}</h3><span class="delta ${up?'up':'down'}">${x.delta_points>0?'+':''}${x.delta_points} pts</span></header><div class="prob-shift"><b>${x.base_probability_percent}%</b><span>→</span><b>${x.simulated_probability_percent}%</b></div><div class="path-box"><b>${path?.hops||0} niveau(x)</b> · ${esc(pathText)}</div></article>`
  }).join(''):'<div class="causal-empty">Cette intervention ne produit pas de déplacement mesurable dans la profondeur choisie.</div>';
}

$('#domainFilter').addEventListener('change',renderGraph);
$('#graphSearch').addEventListener('input',renderGraph);
$('#resetGraph').addEventListener('click',resetGraph);
$('#scenarioForm').addEventListener('submit',runScenario);

loadGraph().catch(err=>{console.error(err);$('#causalStatus').textContent='Graphe indisponible';$('#graphEmpty').textContent=`Impossible de charger le graphe : ${err.message}`});