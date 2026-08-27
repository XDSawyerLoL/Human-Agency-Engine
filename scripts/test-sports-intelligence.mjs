import { sportsLeagueMatchScore } from '../src/sports_intelligence.js';

const bundesliga={strLeague:'German Bundesliga',strLeagueAlternate:'Bundesliga, 1. Bundesliga'};
const bundesliga2={strLeague:'2. Bundesliga',strLeagueAlternate:'German 2. Bundesliga'};
const cup={strLeague:'DFB-Pokal',strLeagueAlternate:'German Cup'};

const exact=sportsLeagueMatchScore(bundesliga,'1. Bundesliga');
const wrongDivision=sportsLeagueMatchScore(bundesliga2,'1. Bundesliga');
const unrelated=sportsLeagueMatchScore(cup,'1. Bundesliga');

if(exact<.55) throw new Error(`expected Bundesliga match, got ${exact}`);
if(unrelated>=.55) throw new Error(`unrelated competition must be rejected, got ${unrelated}`);
if(wrongDivision>=exact) throw new Error('wrong division must not outrank the intended league');

console.log(JSON.stringify({ok:true,exact,wrongDivision,unrelated}));
