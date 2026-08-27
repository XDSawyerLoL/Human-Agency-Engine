import { sportsLeagueMatchScore, zonedKickoffToUtc, predictMatchDetailed } from '../src/sports_intelligence.js';

const bundesliga={strLeague:'German Bundesliga',strLeagueAlternate:'Bundesliga, 1. Bundesliga'};
const bundesliga2={strLeague:'2. Bundesliga',strLeagueAlternate:'German 2. Bundesliga'};
const cup={strLeague:'DFB-Pokal',strLeagueAlternate:'German Cup'};

const exact=sportsLeagueMatchScore(bundesliga,'1. Bundesliga');
const wrongDivision=sportsLeagueMatchScore(bundesliga2,'1. Bundesliga');
const unrelated=sportsLeagueMatchScore(cup,'1. Bundesliga');
if(exact<.55) throw new Error(`expected Bundesliga match, got ${exact}`);
if(unrelated>=.55) throw new Error(`unrelated competition must be rejected, got ${unrelated}`);
if(wrongDivision>=exact) throw new Error('wrong division must not outrank the intended league');

const london=zonedKickoffToUtc('2026-08-28','20:00','Europe/London');
const paris=zonedKickoffToUtc('2026-08-28','20:00','Europe/Paris');
if(london!=='2026-08-28T19:00:00.000Z') throw new Error(`BST kickoff conversion wrong: ${london}`);
if(paris!=='2026-08-28T18:00:00.000Z') throw new Error(`CEST kickoff conversion wrong: ${paris}`);

const model={ratings:new Map([['alpha',1640],['beta',1510]]),home:45,draw:25,away:30,played:97,forms:new Map([['alpha',[3,3,1,3,1]],['beta',[0,1,3,0,1]]])};
const detail=predictMatchDetailed(model,'Alpha FC','Beta FC');
const sum=detail.probabilities.reduce((a,b)=>a+b,0);
if(Math.abs(sum-1)>.000001)throw new Error('sports probabilities do not sum to 1');
if(detail.explanation.home_advantage_elo!==72)throw new Error('home advantage explanation missing');
if(detail.explanation.home_rating!==1640||detail.explanation.away_rating!==1510)throw new Error('Elo explanation missing');
if(detail.explanation.training_matches!==97)throw new Error('training sample explanation missing');
if(!Number.isFinite(detail.explanation.form_probability_shift_points))throw new Error('form shift explanation missing');

console.log(JSON.stringify({ok:true,exact,wrongDivision,unrelated,london,paris,home:Math.round(detail.probabilities[0]*100),draw:Math.round(detail.probabilities[1]*100),away:Math.round(detail.probabilities[2]*100),form_shift:detail.explanation.form_probability_shift_points}));
