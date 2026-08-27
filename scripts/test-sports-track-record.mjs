import { SportsTrackRecord } from '../src/sports_track_record.js';

const track=new SportsTrackRecord(null);
const competition={country:'England',name:'Premier League'};
const fixture={fixture_key:'england|premier league|2026-08-28|alpha|beta',id:'x1',utc_date:'2026-08-28T20:00:00Z',home:'Alpha FC',away:'Beta FC',source:'test',probabilities:{home:.6,draw:.25,away:.15},model_outcome:'home',model_confidence_percent:60};
await track.recordPredictions(competition,[fixture]);
await track.recordPredictions(competition,[{...fixture,probabilities:{home:.1,draw:.1,away:.8},model_outcome:'away',model_confidence_percent:80}]);
let report=await track.report(competition);
if(report.tracked_matches!==1||report.pending_matches!==1)throw new Error('fixture must be recorded once');
if(Math.abs(report.upcoming_tracked[0].p_home-.6)>.0001)throw new Error('first published probability was rewritten');
await track.resolveResults([{fixture_key:fixture.fixture_key,status:'finished',outcome:'home',home_score:2,away_score:1}]);
report=await track.report(competition);
if(report.resolved_matches!==1||report.pending_matches!==0)throw new Error('result not resolved');
if(report.top_pick_accuracy!==1)throw new Error('correct prediction not counted');
if(!(report.multiclass_brier>=0&&report.multiclass_brier<1))throw new Error('Brier missing');
if(Math.abs(report.recent_resolved[0].p_home-.6)>.0001)throw new Error('resolution rewrote frozen probability');
console.log(JSON.stringify({ok:true,brier:report.multiclass_brier,accuracy:report.top_pick_accuracy}));
