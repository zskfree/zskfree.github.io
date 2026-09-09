#!/usr/bin/env python3
import hashlib
import html
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(os.getenv("BRIEF_ROOT", "/opt/daily-ai-power-brief/site/daily-ai-power-brief"))
KEY_FILE = Path(os.getenv("FREELLMAPI_KEY_FILE", "/opt/daily-ai-power-brief/freellmapi.key"))
API_URL = os.getenv("FREELLMAPI_URL", "http://127.0.0.1:3001/v1/audio/speech")
VOICE = os.getenv("TTS_VOICE", "Charon")
SITE_URL = os.getenv("SITE_URL", "https://www.280468.xyz/daily-ai-power-brief")
MODELS = [
    ("gemini-3.1-flash-tts-preview", "wav"),
    ("gemini-2.5-flash-preview-tts", "wav"),
]


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run(cmd, check=True):
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def content_hash(data):
    payload = json.dumps({"news": data.get("news", []), "podcast_script": data.get("podcast_script", "")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def split_text(text, limit=850):
    paras = [p.strip() for p in text.replace("\r", "").split("\n") if p.strip()]
    out, buf = [], ""
    for p in paras:
        parts = [p[i:i + limit] for i in range(0, len(p), limit)] if len(p) > limit else [p]
        for part in parts:
            if buf and len(buf) + len(part) + 1 > limit:
                out.append(buf)
                buf = part
            else:
                buf = f"{buf}\n{part}".strip()
    if buf:
        out.append(buf)
    return out or [text]


def read_key():
    if KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    db_path = Path("/var/lib/docker/volumes/freellmapi_freellmapi-data/_data/freeapi.db")
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'unified_api_key'").fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    raise RuntimeError("FreeLLMAPI unified API key is unavailable")


def request_tts(text, model, response_format, key, target):
    body = json.dumps({"model": model, "input": text, "voice": VOICE, "response_format": response_format}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "daily-ai-power-brief/1.0"})
    with urllib.request.urlopen(req, timeout=240) as resp:
        raw = resp.read()
        ctype = (resp.headers.get("Content-Type") or "application/octet-stream").lower()
        routed = resp.headers.get("X-Routed-Via") or model
    if len(raw) < 1500:
        raise RuntimeError(f"audio payload too small ({len(raw)} bytes)")
    target.write_bytes(raw)
    return ctype, routed


def normalize(raw_path, ctype, out_path):
    if "pcm" in ctype or "l16" in ctype:
        cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw_path), "-ar", "44100", "-ac", "1", "-b:a", "96k", str(out_path)]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-ar", "44100", "-ac", "1", "-b:a", "96k", str(out_path)]
    run(cmd)
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(out_path)])
    duration = float(probe.stdout.strip() or 0)
    if duration < 0.5 or out_path.stat().st_size < 1500:
        raise RuntimeError("normalized audio failed validation")
    return duration


def synth_segment(text, idx, work, key):
    errors = []
    for model, fmt in MODELS:
        for attempt in range(1, 4):
            raw = work / f"seg-{idx:02d}-{attempt}.raw"
            mp3 = work / f"seg-{idx:02d}.mp3"
            try:
                ctype, routed = request_tts(text, model, fmt, key, raw)
                duration = normalize(raw, ctype, mp3)
                log(f"segment {idx}: {routed} OK ({duration:.1f}s)")
                return mp3, routed
            except Exception as e:
                errors.append(f"{model}#{attempt}:{type(e).__name__}:{e}")
                log(f"segment {idx}: {model} attempt {attempt} failed")
                time.sleep(3 * attempt)
    raise RuntimeError("; ".join(errors))


def concat_segments(parts, output, work):
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "libmp3lame", "-b:a", "96k", "-ar", "44100", "-ac", "1", str(output)])
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)])
    return float(probe.stdout.strip() or 0)


def render_post(data):
    date = html.escape(data.get("date", "")); title = html.escape(data.get("title", "AI 与电力每日简报")); summary = html.escape(data.get("summary", ""))
    blocks = []
    for i, n in enumerate(data.get("news", []), 1):
        source = n.get("source_url") or n.get("source") or ""
        link = f'<p><a href="{html.escape(source)}" rel="noopener">原始来源</a></p>' if source.startswith("http") else ""
        image = n.get("image_url") or ""
        img = f'<img style="width:100%;max-height:420px;object-fit:cover;border-radius:14px" src="{html.escape(image)}" alt="">' if image.startswith("http") else ""
        blocks.append(f'<section><h2>{i}. {html.escape(str(n.get("title", "")))}</h2>{img}<p>{html.escape(str(n.get("summary", "")))}</p><p><strong>影响：</strong>{html.escape(str(n.get("impact", "")))}</p><p><strong>与你的相关性：</strong>{html.escape(str(n.get("career_relevance", "")))}</p>{link}</section>')
    audio = f'<audio controls preload="none" src="../audio/{date}.mp3"></audio>'
    return f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.75}}section{{border-top:1px solid #ddd;margin-top:22px;padding-top:14px}}audio{{width:100%}}</style><h1>{title}</h1><p>{date}</p>{audio}<p><strong>今日判断：</strong>{summary}</p>{"".join(blocks)}'


def build_feed(records):
    items = []
    for d in sorted(records, key=lambda x: x.get("date", ""), reverse=True)[:90]:
        date = d.get("date", ""); title = d.get("title", f"AI 与电力每日简报｜{date}"); desc = d.get("summary", "")
        mp3 = ROOT / "audio" / f"{date}.mp3"; length = mp3.stat().st_size if mp3.exists() else 0
        try:
            pub = datetime.strptime(date, "%Y-%m-%d").replace(hour=8, tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(f"<item><title>{escape(title)}</title><description>{escape(desc)}</description><guid isPermaLink=\"false\">brief-{escape(date)}</guid><pubDate>{pub}</pubDate><link>{SITE_URL}/posts/{escape(date)}.html</link><enclosure url=\"{SITE_URL}/audio/{escape(date)}.mp3\" length=\"{length}\" type=\"audio/mpeg\" /></item>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>AI 与电力每日简报</title><link>'+SITE_URL+'/</link><description>聚焦 AI、科技与自动化，以及中国电力市场、售电与能源行业的每日个人简报。</description><language>zh-cn</language><itunes:author>AI 与电力每日简报</itunes:author><itunes:explicit>false</itunes:explicit><atom:link href="'+SITE_URL+'/feed.xml" rel="self" type="application/rss+xml" />'+''.join(items)+'</channel></rss>\n'


def process_one(src, key):
    data = json.loads(src.read_text(encoding="utf-8")); date = data["date"]; script = data.get("podcast_script", "").strip()
    if not script:
        raise RuntimeError(f"{src.name}: missing podcast_script")
    digest = content_hash(data); out_json = ROOT / "data" / f"{date}.json"
    if out_json.exists():
        old = json.loads(out_json.read_text(encoding="utf-8"))
        if old.get("content_hash") == digest and (ROOT / "audio" / f"{date}.mp3").exists():
            return False
    with tempfile.TemporaryDirectory(prefix="brief-tts-") as td:
        work = Path(td); segments = split_text(script); parts = []; routed = []
        for i, segment in enumerate(segments, 1):
            mp3, model = synth_segment(segment, i, work, key); parts.append(mp3); routed.append(model)
        audio_path = ROOT / "audio" / f"{date}.mp3"; audio_path.parent.mkdir(parents=True, exist_ok=True)
        duration = concat_segments(parts, audio_path, work)
    data["content_hash"] = digest; data["audio_url"] = f"./audio/{date}.mp3"; data["audio_duration_seconds"] = round(duration, 1); data["tts_models_used"] = routed
    (ROOT / "data").mkdir(parents=True, exist_ok=True); out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (ROOT / "data" / "latest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (ROOT / "posts").mkdir(parents=True, exist_ok=True); (ROOT / "posts" / f"{date}.html").write_text(render_post(data), encoding="utf-8")
    log(f"published {date}, {duration:.1f}s, {len(segments)} segments")
    return True


def main():
    for tool in ("ffmpeg", "ffprobe", "git"):
        if not shutil.which(tool):
            raise RuntimeError(f"missing dependency: {tool}")
    key = read_key(); inbox = ROOT / "inbox"; inbox.mkdir(parents=True, exist_ok=True)
    changed = False
    for src in sorted(inbox.glob("*.json")):
        changed = process_one(src, key) or changed
    records = []
    for path in (ROOT / "data").glob("20??-??-??.json"):
        try: records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception: pass
    if records:
        (ROOT / "feed.xml").write_text(build_feed(records), encoding="utf-8")
    log("done" + (" (changes generated)" if changed else " (no new content)"))


if __name__ == "__main__":
    try: main()
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
