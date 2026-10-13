"""HORIZON: programme independent B2B text posts with Metricool.
Dry-run unless all credentials and explicit autoload variable are present.
No unsupported predictive claims or private API keys in public code.
"""
import datetime as dt, json, os, sys, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
STATE = HERE / "state.json"
TARGET = "https://future-engine-predictor-398116.hostingersite.com/plans"
TIMEZONE = ZoneInfo("Europe/Paris")
CHANNELS = {"linkedin", "facebook", "threads"}

def next_business_slot(now):
    local = now.astimezone(TIMEZONE)
    slot = local.replace(hour=11, minute=15, second=0, microsecond=0)
    if slot <= local: slot += dt.timedelta(days=1)
    while slot.weekday() >= 5: slot += dt.timedelta(days=1)
    return slot

def message(topic, channel):
    params = urllib.parse.urlencode({
        "utm_source": channel, "utm_medium": "organic_social",
        "utm_campaign": "horizon_b2b", "utm_content": topic["id"]})
    return "\n\n".join([topic["hook"], topic["body"],
        "Source de référence : " + topic["source"],
        "HORIZON : " + TARGET + "?" + params])

def make_post(topic, channel, at):
    if channel not in CHANNELS: raise ValueError("Text channels only")
    data = {
        "publicationDate": {"dateTime": at.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": "Europe/Paris"},
        "text": message(topic, channel), "providers": [{"network": channel}],
        "autoPublish": True, "draft": False}
    field = {"linkedin":"linkedinData", "facebook":"facebookData", "threads":"threadsData"}[channel]
    data[field] = {"type":"POST"} if channel == "facebook" else ({"type":"post"} if channel == "linkedin" else {})
    return data

def metricool_post(body):
    params = urllib.parse.urlencode({"userId":os.environ["METRICOOL_USER_ID"],
        "blogId":os.environ["METRICOOL_BLOG_ID"]})
    req = urllib.request.Request("https://app.metricool.com/api/v2/scheduler/posts?" + params,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json", "X-Mc-Auth":os.environ["METRICOOL_API_TOKEN"]},
        method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        obj=json.loads(r.read().decode("utf-8"))
    if not isinstance(obj, dict): raise ValueError("Invalid API reply")
    return obj

def run():
    topics = json.loads((HERE / "topics.json").read_text("utf-8"))
    status = json.loads(STATE.read_text("utf-8"))
    channels = [x.strip() for x in os.environ.get("METRICOOL_NETWORKS","linkedin").split(",") if x.strip()]
    if not channels or any(x not in CHANNELS for x in channels):
        raise ValueError("Unsupported network: video channels require video files")
    chosen = next((x for x in topics if any(x["id"]+":"+n not in status["scheduled"] for n in channels)), None)
    if chosen is None:
        print(json.dumps({"status":"finished","topics":len(topics)})); return
    at = next_business_slot(dt.datetime.now(dt.timezone.utc))
    configured = all(os.environ.get(x) for x in (
        "METRICOOL_API_TOKEN","METRICOOL_USER_ID","METRICOOL_BLOG_ID"))
    if not (configured and os.environ.get("METRICOOL_AUTOPUBLISH") == "1"):
        print(json.dumps({"status":"dry_run","topic":chosen["id"],"slot":at.isoformat(),
            "channels":channels,"reason":"Connections or explicit authorization missing"},ensure_ascii=False)); return
    failures = []
    for network in channels:
        key=chosen["id"]+":"+network
        if key in status["scheduled"]: continue
        try:
            result = metricool_post(make_post(chosen,network,at))
            status["scheduled"][key] = {"date":at.isoformat(),"id":str(result.get("id",""))}
            tmp=STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n","utf-8")
            tmp.replace(STATE)
        except Exception as error:
            failures.append({"network":network,"type":type(error).__name__})
    print(json.dumps({"status":"partial" if failures else "scheduled",
        "topic":chosen["id"],"errors":failures},ensure_ascii=False))
    if failures: sys.exit(1)

if __name__ == "__main__": run()
