import { sportsLeagueMatchScore, zonedKickoffToUtc } from '../src/sports_intelligence.js';

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

console.log(JSON.stringify({ok:true,exact,wrongDivision,unrelated,london,paris}));
