const $=s=>document.querySelector(s);
let graph=null;
let selectedNode=null;

const esc=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const domainLabels={natural_hazards:'Risques naturels',weather_climate:'Climat & météo',cyber_technology:'Technologie & cyber',public_health:'Santé publique',financial_stress:'Stress financier',energy:'Énergie',economy_labor:'Économie & emploi',supply_fuel:'Approvisionnement',social_collective_behavior:'Comportements collectifs',geopolitics_security:'Géopolitique & sécurité',regulation_policy:'Régulation & politiques',transport_mobility:'Transport & mobilité'};
function fmt(n){return new Intl.NumberFormat('fr-FR').format(Number(n)||0)}

async function loadGraph(){
  const res=await fetch('/api/causal-graph',{cache:'no-store'});
  if(!res.ok) throw new Error(`HTTP ${res.status}`);
  graph=await res.json();
  const learned=Number(graph.learning?.active_transitions||0);
  $('#causalStatus').textContent=`Causal World · ${learned} lien${learned>1?'s':''} apprenant${learned>1?'s':''} · ${new Date(graph.generated_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
  renderMetrics();populateControls();renderLeverage();renderGraph();
}
function renderMetrics(){const m=graph.metrics||{},values=[m.nodes,m.edges,m.forecast_nodes,m.learned_structural_edges];[...document.querySelectorAll('#causalMetrics strong')].forEach((el,i)=>el.textContent=fmt(values[i]));}
function populateControls(){
  const domains=[...new Set((graph.nodes||[]).filter(n=>n.type==='forecast'&&n.domain).map(n=>n.domain))].sort();
  $('#domainFilter').innerHTML='<option value="">Tous les domaines</option>'+domains.map(d=>`<option value="${esc(d)}">${esc(domainLabels[d]||d)}</option>`).join('');
  const leverage=graph.metrics?.top_leverage||[];
  const domainOpts=domains.map(d=>`<option value="domain:${esc(d)}">DOMAINE · ${esc(domainLabels[d]||d)}</option>`).join('');
  const nodeOpts=leverage.map(n=>`<option value="${esc(n.node_id)}">${n.type==='forecast'?'SCÉNARIO':'MÉCANISME'} · ${esc(n.label.slice(0,90))}</option>`).join('');
  $('#scenarioTarget').innerHTML='<option value="">Choisir un point de levier…</option>'+domainOpts+nodeOpts;
}
function renderLeverage(){const rows=graph.metrics?.top_leverage||[];$('#leverageList').innerHTML=rows.length?rows.slice(0,8).map((x,i)=>`<div class="leverage-item" data-node="${esc(x.node_id)}"><div><strong>${String(i+1).padStart(2,'0')} · ${esc(x.label)}</strong><span>${esc(x.type==='forecast'?(domainLabels[x.domain]||x.domain||'Scénario'):'Mécanisme')} · ${x.downstream_nodes} nœuds en aval</span></div><span class="leverage-score">${Number(x.leverage_score).toFixed(2)}</span></div>`).join(''):'<div class="causal-empty">Aucun point de levier disponible.</div>';document.querySelectorAll('.leverage-item').forEach(el=>el.addEventListener('click',()=>inspectNode(el.dataset.node,true)));}
function node(id){return (graph.nodes||[]).find(n=>n.id===id)}
function incoming(id){return (graph.edges||[]).filter(e=>e.to===id)}
function relationBadge(e){if(!e)return'';const learned=e.learning?.active?`<span class="flow-learned">APPRIS · n=${e.learning.samples}</span>`:'';const strength=Number.isFinite(Number(e.strength))?`<span>${Math.round(Number(e.strength)*100)}%</span>`:'';return `<small class="flow-edge-meta">${strength}${learned}</small>`;}
function chainForForecast(f){
  const mechanisms=[],sources=[],upstreamForecasts=[],queue=incoming(f.id).map(edge=>({edge,depth:0}));
  const seenEdges=new Set(),seenNodes=new Set([f.id]);let guard=0;
  while(queue.length&&guard<160){guard++;const {edge,depth}=queue.shift();const edgeKey=`${edge.from}->${edge.to}:${edge.type||''}`;if(seenEdges.has(edgeKey))continue;seenEdges.add(edgeKey);const n=node(edge.from);if(!n)continue;
    if(n.type==='source'){sources.push({node:n,edge,depth});continue;}
    if(n.type==='concept'){mechanisms.push({node:n,edge,depth});if(depth<6&&!seenNodes.has(n.id)){seenNodes.add(n.id);for(const prev of incoming(n.id))queue.push({edge:prev,depth:depth+1});}continue;}
    if(n.type==='forecast'){upstreamForecasts.push({node:n,edge,depth});if(depth<4&&!seenNodes.has(n.id)){seenNodes.add(n.id);for(const prev of incoming(n.id))queue.push({edge:prev,depth:depth+1});}}
  }
  const uniq=(rows,limit)=>{const seen=new Set();return rows.sort((a,b)=>a.depth-b.depth||(Number(b.edge?.strength)||0)-(Number(a.edge?.strength)||0)).filter(x=>!seen.has(x.node.id)&&seen.add(x.node.id)).slice(0,limit)};
  return {mechanisms:uniq(mechanisms,4),sources:uniq(sources,4),upstreamForecasts:uniq(upstreamForecasts,2)};
}
function filteredForecasts(){
  const domain=$('#domainFilter').value,q=$('#graphSearch').value.trim().toLowerCase();
  let rows=(graph.nodes||[]).filter(n=>n.type==='forecast'&&(!domain||n.domain===domain));
  if(q)rows=rows.filter(n=>{const c=chainForForecast(n);return String(n.label).toLowerCase().includes(q)||c.mechanisms.some(x=>String(x.node.label).toLowerCase().includes(q))||c.sources.some(x=>String(x.node.label).toLowerCase().includes(q))||c.upstreamForecasts.some(x=>String(x.node.label).toLowerCase().includes(q));});
  rows.sort((a,b)=>(Number(b.probability_percent)||0)-(Number(a.probability_percent)||0));
  if(domain||q)return rows.slice(0,12);
  const perDomain=new Set(),out=[];for(const f of rows){if(perDomain.has(f.domain))continue;perDomain.add(f.domain);out.push(f);if(out.length>=12)break;}return out;
}
function flowNode(n,kind,edge){return `<button class="flow-node ${kind}" data-node="${esc(n.id)}" type="button"><span>${esc(n.label)}</span>${relationBadge(edge)}</button>`;}
function renderGraph(){
  if(!graph)return;const stage=$('#graphStage'),svg=$('#causalGraph');if(svg)svg.hidden=true;stage.querySelector('.causal-flow-board')?.remove();
  const forecasts=filteredForecasts();const board=document.createElement('div');board.className='causal-flow-board';
  board.innerHTML=forecasts.length?forecasts.map(f=>{const c=chainForForecast(f),domain=domainLabels[f.domain]||f.domain||'Domaine';const upstream=c.upstreamForecasts.length?`<div class="flow-upstream"><small>SCÉNARIOS AMONT / LIENS APPRIS</small>${c.upstreamForecasts.map(x=>flowNode(x.node,'forecast upstream',x.edge)).join('')}</div>`:'';return `<article class="causal-flow-row" data-forecast="${esc(f.id)}"><header><span>${esc(domain)}</span><strong>${Number(f.probability_percent)||'—'}%</strong></header><div class="flow-lane sources"><small>SOURCES / SIGNAUX</small>${c.sources.length?c.sources.map(x=>flowNode(x.node,'source',x.edge)).join(''):'<div class="flow-empty">Aucune source amont traçable</div>'}</div><div class="flow-arrow">→</div><div class="flow-lane mechanisms"><small>MÉCANISMES</small>${c.mechanisms.length?c.mechanisms.map(x=>flowNode(x.node,'concept',x.edge)).join(''):'<div class="flow-empty">Conséquence directe</div>'}${upstream}</div><div class="flow-arrow">→</div><div class="flow-lane forecast"><small>CONSÉQUENCE PRÉDITE</small>${flowNode(f,'forecast',null)}</div></article>`}).join(''):'<div class="causal-empty">Aucune chaîne ne correspond à ce filtre.</div>';
  stage.appendChild(board);$('#graphEmpty').hidden=forecasts.length>0;board.querySelectorAll('[data-node]').forEach(el=>el.addEventListener('click',()=>inspectNode(el.dataset.node,false)));if(selectedNode)highlight(selectedNode);
}
function inspectNode(id,setTarget){selectedNode=id;const n=node(id);if(!n)return;const inEdges=incoming(id),outEdges=(graph.edges||[]).filter(e=>e.from===id),learned=[...inEdges,...outEdges].filter(e=>e.learning?.active);const kind=n.type==='forecast'?'Scénario prédictif':n.type==='source'?'Source observée':'Mécanisme causal hypothétique';const detail=n.type==='forecast'?`${n.probability_percent}% · ${domainLabels[n.domain]||n.domain} · ${n.horizon_tier||'horizon non défini'}`:`${inEdges.length} liens entrants · ${outEdges.length} liens sortants`;const learningText=learned.length?` ${learned.length} lien(s) voisin(s) ont une force ajustée par l’historique résolu.`:'';$('#nodeInspector').innerHTML=`<small>${esc(kind.toUpperCase())}</small><strong>${esc(n.label)}</strong><p>${esc(detail)}.${esc(learningText)} ${n.type==='forecast'?'La probabilité affichée reste celle du moteur public, pas celle d’une simulation.':'Une association apprise reste distincte d’une preuve causale.'}</p>`;if(setTarget){const opt=[...$('#scenarioTarget').options].find(o=>o.value===id);if(opt)$('#scenarioTarget').value=id;}highlight(id);}
function highlight(id){document.querySelectorAll('.flow-node').forEach(el=>el.classList.toggle('graph-dim',el.dataset.node!==id));document.querySelectorAll(`.flow-node[data-node="${CSS.escape(id)}"]`).forEach(el=>el.classList.remove('graph-dim'));const neighbors=new Set([id]);for(const e of graph.edges||[])if(e.from===id||e.to===id){neighbors.add(e.from);neighbors.add(e.to)}document.querySelectorAll('.flow-node').forEach(el=>{if(neighbors.has(el.dataset.node))el.classList.remove('graph-dim')});}
function resetGraph(){selectedNode=null;$('#domainFilter').value='';$('#graphSearch').value='';renderGraph();$('#nodeInspector').innerHTML='<small>SÉLECTION</small><strong>Cliquez sur une carte</strong><p>Providence affiche ici la source, le mécanisme ou la conséquence sélectionnée.</p>'}
async function runScenario(ev){ev.preventDefault();const target=$('#scenarioTarget').value;if(!target)return;const button=$('.scenario-run');button.disabled=true;button.textContent='Propagation…';try{const res=await fetch('/api/scenario-lab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interventions:[{target,direction:$('#scenarioDirection').value,strength:Number($('#scenarioStrength').value)}],max_hops:Number($('#scenarioHops').value)})});const data=await res.json();if(!res.ok)throw new Error(data.error||`HTTP ${res.status}`);renderScenario(data);}catch(err){$('#scenarioSummary').innerHTML=`<p>Simulation indisponible : ${esc(err.message)}</p>`;$('#scenarioResults').innerHTML='<div class="causal-empty">Aucun résultat.</div>'}finally{button.disabled=false;button.innerHTML='Propager le scénario →'}}
function renderScenario(data){const s=data.summary||{},learning=data.learning?.active_transitions?` · ${data.learning.active_transitions} transitions apprenantes`:'';$('#scenarioSummary').innerHTML=`<p><strong>${fmt(s.affected)} scénarios affectés</strong> · ${fmt(s.second_order_effects)} effets de second ordre · déplacement maximal ${fmt(s.max_absolute_delta_points)} points${esc(learning)}. Les valeurs simulées restent hors Track Record.</p>`;$('#resultMeta').textContent=`${data.max_hops} niveaux · ${data.mode}`;const rows=data.affected_forecasts||[];$('#scenarioResults').innerHTML=rows.length?rows.slice(0,12).map(x=>{const up=x.delta_points>=0,path=x.paths?.[0],pathText=path?.path?.map(p=>p.label).join(' → ')||'Intervention directe';return `<article class="result-card"><header><h3>${esc(x.title)}</h3><span class="delta ${up?'up':'down'}">${x.delta_points>0?'+':''}${x.delta_points} pts</span></header><div class="prob-shift"><b>${x.base_probability_percent}%</b><span>→</span><b>${x.simulated_probability_percent}%</b></div><div class="path-box"><b>${path?.hops||0} niveau(x)</b> · ${esc(pathText)}</div></article>`}).join(''):'<div class="causal-empty">Cette intervention ne produit pas de déplacement mesurable dans la profondeur choisie.</div>';}
$('#domainFilter').addEventListener('change',renderGraph);$('#graphSearch').addEventListener('input',renderGraph);$('#resetGraph').addEventListener('click',resetGraph);$('#scenarioForm').addEventListener('submit',runScenario);
loadGraph().catch(err=>{console.error(err);$('#causalStatus').textContent='Causal World indisponible';$('#graphEmpty').textContent=`Impossible de charger le modèle : ${err.message}`});