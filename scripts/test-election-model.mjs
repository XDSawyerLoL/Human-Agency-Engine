import { parseElectionPollingHtml, buildElectionModel } from '../src/election_model.js';

const html=`
<table class="wikitable">
<tr><th>Sondeur</th><th>Échantillon</th><th>Alice Martin</th><th>Bruno Durand</th><th>Claire Robert</th><th>David Simon</th></tr>
<tr><td>IFOP</td><td>1500</td><td>31%</td><td>27%</td><td>23%</td><td>19%</td></tr>
<tr><td>IPSOS</td><td>1200</td><td>30%</td><td>28%</td><td>22%</td><td>20%</td></tr>
<tr><td>Harris</td><td>1800</td><td>32%</td><td>26%</td><td>24%</td><td>18%</td></tr>
<tr><td>Elabe</td><td>1000</td><td>29%</td><td>29%</td><td>23%</td><td>19%</td></tr>
<tr><td>OpinionWay</td><td>1400</td><td>31%</td><td>27%</td><td>22%</td><td>20%</td></tr>
</table>
<table class="wikitable">
<tr><th>Sondeur</th><th>Échantillon</th><th>Alice Martin</th><th>Bruno Durand</th></tr>
<tr><td>IFOP</td><td>1200</td><td>53%</td><td>47%</td></tr>
<tr><td>IPSOS</td><td>1600</td><td>52%</td><td>48%</td></tr>
<tr><td>Harris</td><td>1100</td><td>54%</td><td>46%</td></tr>
</table>`;

const plainNumericHtml=`
<table class="wikitable">
<tr><th rowspan="2">Sondeur</th><th rowspan="2">Échantillon</th><th colspan="4">Intentions de vote</th></tr>
<tr><th>Alice Martin</th><th>Bruno Durand</th><th>Claire Robert</th><th>David Simon</th></tr>
<tr><td>IFOP</td><td>1500</td><td>31</td><td>27</td><td>23</td><td>19</td></tr>
<tr><td>IPSOS</td><td>1200</td><td>30</td><td>28</td><td>22</td><td>20</td></tr>
<tr><td>Harris</td><td>1800</td><td>32</td><td>26</td><td>24</td><td>18</td></tr>
<tr><td>Elabe</td><td>1000</td><td>29</td><td>29</td><td>23</td><td>19</td></tr>
<tr><td>OpinionWay</td><td>1400</td><td>31</td><td>27</td><td>22</td><td>20</td></tr>
</table>`;

const parsed=parseElectionPollingHtml(html);
if(parsed.polls.length<5)throw new Error(`first round polling parse failed: ${parsed.polls.length}`);
if(parsed.matchups.length<3)throw new Error(`head to head parse failed: ${parsed.matchups.length}`);
const plain=parseElectionPollingHtml(plainNumericHtml);
if(plain.polls.length<5)throw new Error(`plain numeric polling parse failed: ${plain.polls.length}`);
if((plain.polls[0]?.candidates||[]).length<4)throw new Error('rowspan/colspan candidate alignment failed');

const originalFetch=globalThis.fetch;
globalThis.fetch=async input=>{
  const url=String(input);
  if(url.includes('fr.wikipedia.org/w/api.php'))return new Response(JSON.stringify({parse:{text:{'*':html}}}),{status:200,headers:{'content-type':'application/json'}});
  throw new Error(`unexpected fetch ${url}`);
};

try{
  const model=await buildElectionModel('Que va-t-il se passer pour les élections 2027 en France ?',{now:Date.UTC(2026,8,5)});
  if(model.schema!=='providence-election-model-v1'||model.status!=='ok')throw new Error(`model unavailable: ${model.status}`);
  if((model.first_round?.candidates||[]).length<4)throw new Error('candidate aggregation missing');
  const qual=model.first_round.candidates.reduce((s,x)=>s+Number(x.qualification_probability||0),0);
  if(Math.abs(qual-200)>.6)throw new Error(`qualification probabilities should sum to 200, got ${qual}`);
  const pairTotal=model.first_round.pair_scenarios.reduce((s,x)=>s+Number(x.probability_percent||0),0);
  if(Math.abs(pairTotal-100)>.7)throw new Error(`pair scenarios should sum to 100, got ${pairTotal}`);
  if(!model.second_round?.length)throw new Error('head-to-head model missing');
  const h2h=model.second_round[0].model_win_probability.reduce((s,x)=>s+Number(x.percent||0),0);
  if(Math.abs(h2h-100)>.2)throw new Error(`head-to-head probability normalization failed: ${h2h}`);
  if(model.methodology.house_effects_applied!==false||model.methodology.historical_calibration_applied!==false)throw new Error('unvalidated calibration was applied');
  if(model.guardrails.lobbying_not_direct_vote_shift!==true||model.guardrails.polls_are_not_votes!==true)throw new Error('election guardrails missing');
  console.log(JSON.stringify({ok:true,polls:parsed.polls.length,plain_numeric_polls:plain.polls.length,candidates:model.first_round.candidates.length,iterations:model.methodology.monte_carlo_iterations,top:model.first_round.candidates[0],top_pair:model.first_round.pair_scenarios[0],head_to_head:model.second_round[0]}));
} finally {globalThis.fetch=originalFetch;}
