"""Browser console script for extracting liked videos from TikTok."""
from __future__ import annotations
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Paste this into the browser console while on your TikTok liked-videos page.
# It scrolls automatically, collects up to 1000 video entries, then downloads
# wholikedit_likes.json which the app can import.
JS_SNIPPET = r"""(async () => {
  const MAX = 1000, PAUSE = 1800;
  const found = new Map();
  let stale = 0;

  const harvest = () => {
    document.querySelectorAll('a[href*="/video/"]').forEach(a => {
      const m = a.href.match(/\/@([^/?#]+)\/video\/(\d+)/);
      if (!m) return;
      const [, author, id] = m;
      if (found.has(id)) return;
      const img = a.querySelector('img');
      found.set(id, {
        id, author,
        url: `https://www.tiktok.com/@${author}/video/${id}`,
        thumbnail: img?.src ?? null,
        description: img?.alt ?? '',
      });
    });
  };

  console.log('[WhoLikedIt?] Starting — page will scroll automatically...');
  while (found.size < MAX && stale < 6) {
    const before = found.size;
    harvest();
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, PAUSE));
    stale = found.size === before ? stale + 1 : 0;
    if (found.size !== before)
      console.log(`[WhoLikedIt?] ${found.size} videos found so far...`);
  }

  const videos = [...found.values()];
  console.log(`[WhoLikedIt?] Done: ${videos.length} videos extracted.`);

  const blob = new Blob(
    [JSON.stringify({version: 1, videos}, null, 2)],
    {type: 'application/json'}
  );
  Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: 'wholikedit_likes.json',
  }).click();
  console.log('[WhoLikedIt?] "wholikedit_likes.json" downloaded!');
})();"""


def parse_likes_file(path: Path) -> list[dict]:
    """Parse the JSON exported by JS_SNIPPET. Returns list of video dicts."""
    try:
        data = json.loads(path.read_text("utf-8"))
        videos = data.get("videos", [])
        log.info("Parsed %d liked videos from %s", len(videos), path.name)
        return videos
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        log.error("Failed to parse likes file %s: %s", path, exc)
        return []
