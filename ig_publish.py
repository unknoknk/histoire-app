"""Publication d'un Reel Instagram depuis une tâche planifiée cloud (Claude Code), sans jeton dans le dépôt.

Le jeton est ajouté par le proxy d'Anthropic (network secret, hôte graph.instagram.com, en-tête
« Authorization: Bearer … ») ; en local, définir IG_TOKEN pour tester.

    python3 ig_publish.py --check          # vérifie l'accès API (GET /me)
    python3 ig_publish.py JOB              # publie jobs/JOB.json (vidéo videos/… sur la branche media)

jobs/JOB.json : {"account": "aundetailpress", "user_id": "…", "video": "videos/x.mp4", "caption": "…"}
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IG_GRAPH = "https://graph.instagram.com/v23.0"
MEDIA_RAW = "https://raw.githubusercontent.com/unknoknk/histoire-app/media/"
HEADERS = {"Authorization": f"Bearer {os.environ['IG_TOKEN']}"} if os.environ.get("IG_TOKEN") else {}


def http(method, url, data=None):
    body, h = None, dict(HEADERS)
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {"raw": raw.decode(errors="replace")[:500]}


def check():
    me = http("GET", f"{IG_GRAPH}/me?fields=username,user_id")
    if "username" not in me:
        sys.exit(f"ECHEC accès API Instagram : {me}")
    print(f"OK accès API Instagram : @{me['username']} (user_id {me['user_id']})")


def already_published(uid, caption):
    """Évite un doublon si l'autre canal (tâche Windows) a déjà publié : même première ligne de légende récente."""
    first = caption.strip().splitlines()[0].strip()
    recent = http("GET", f"{IG_GRAPH}/{uid}/media?" + urllib.parse.urlencode({"fields": "caption,permalink,timestamp", "limit": "10"}))
    for m in recent.get("data", []):
        if (m.get("caption") or "").strip().splitlines()[:1] == [first]:
            return m.get("permalink", m.get("id"))
    return None


def publish(job_name):
    job = json.loads((ROOT / "jobs" / f"{job_name}.json").read_text(encoding="utf-8"))
    uid, caption = job["user_id"], job["caption"]
    video_url = MEDIA_RAW + job["video"]
    dup = already_published(uid, caption)
    if dup:
        print(f"DEJA PUBLIE (aucune action) : {dup}")
        return
    print(f"Création du conteneur Reel pour @{job['account']} : {video_url}", flush=True)
    c = http("POST", f"{IG_GRAPH}/{uid}/media", {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"})
    if "id" not in c:
        sys.exit(f"ECHEC création Instagram : {c}")
    st = {}
    for _ in range(100):  # traitement côté Instagram (jusqu'à ~8 min)
        st = http("GET", f"{IG_GRAPH}/{c['id']}?fields=status_code,status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            sys.exit(f"ECHEC Instagram a refusé la vidéo : {st}")
        time.sleep(5)
    else:
        sys.exit(f"ECHEC Instagram traite encore la vidéo : {st}")
    pub = http("POST", f"{IG_GRAPH}/{uid}/media_publish", {"creation_id": c["id"]})
    if "id" not in pub:
        sys.exit(f"ECHEC publication Instagram : {pub}")
    link = http("GET", f"{IG_GRAPH}/{pub['id']}?fields=permalink")
    print(f"PUBLIE sur @{job['account']} : {link.get('permalink', pub['id'])}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    check() if sys.argv[1] == "--check" else publish(sys.argv[1])
