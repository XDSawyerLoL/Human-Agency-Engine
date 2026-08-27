import { refreshSportsTrackRecord } from './sports_intelligence.js';

const HOUR=3_600_000;
const run=()=>refreshSportsTrackRecord().then(x=>console.log(JSON.stringify({event:'sports_track_refresh',tracked:x.tracked,leagues:x.leagues}))).catch(error=>console.error('[sports-track-refresh]',String(error?.message||error)));

// Leave the main world snapshot time to boot first, then seed/resolve sports independently.
setTimeout(run,60_000).unref();
setInterval(run,HOUR).unref();
