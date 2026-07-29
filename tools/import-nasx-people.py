#!/usr/bin/env python3
"""Extract NASx fellow and mentor rosters from the live Squarespace pages.

Not part of the Quarto build. Run it when a new cohort is published, then paste
the emitted blocks into the cohort pages under pages/fellowships/nasx/.

Squarespace stores the two groups differently:

  * Fellows sit inside a `data-current-context="{...}"` JSON attribute on each
    carousel block, as userItems[] with title / description / image.assetUrl.
  * Mentors are hand-laid fluid-engine blocks: an image block followed by a
    sibling text block holding <strong>Name</strong> plus role paragraphs.

Photos are paired with people by *position*, never by filename -- the CDN
filenames are frequently someone else's name (Chetna Anjali's headshot is filed
under "... - Pranav Bhosale.jpeg").

Usage:
    # 1. cache the source pages
    mkdir -p .cache/nasx
    for s in network-for-advanced-study-of-technology-geopolitics \
             network-for-advanced-study-of-technology-geopolitics-2425 \
             network-for-advanced-study-of-pakistan-nasp \
             network-for-advanced-study-of-china-nasc; do
      curl -sSL -A Mozilla/5.0 -o ".cache/nasx/$s.html" \
        "https://legion.takshashila.org.in/$s"
    done

    # 2. extract
    python3 tools/import-nasx-people.py --html-dir .cache/nasx --out-dir .cache/nasx-out

    # 3. fetch photos listed in the emitted images.tsv
    while IFS=$'\t' read -r dest url; do
      mkdir -p "$(dirname "$dest")"
      curl -sS -H 'Accept: image/webp,*/*' -o "$dest" "$url?format=300w"
    done < .cache/nasx-out/images.tsv
"""

import argparse
import html
import json
import pathlib
import re
import sys
import unicodedata

# Source page -> the groups to pull from it, in document order.
#
# "fellows" groups are matched against the carousel JSON blobs on the page, in
# order of appearance. "mentors" groups slice the ordered image/text pairs; the
# slice bounds are given as (start_after_heading, count) where the heading is
# the nearest preceding text block, or None to take the first unclaimed run.
PAGES = {
    "network-for-advanced-study-of-technology-geopolitics": {
        "fellows": ["nast-fellows-2526"],
        "mentors": [("nast-mentors", "Mentors", 14)],
    },
    "network-for-advanced-study-of-technology-geopolitics-2425": {
        "fellows": ["nast-fellows-2425"],
        "mentors": [],
    },
    "network-for-advanced-study-of-pakistan-nasp": {
        "fellows": ["nasp-fellows-2425", "nasp-fellows-pioneer"],
        "mentors": [("nasp-mentors", "Mentors", 12)],
    },
    "network-for-advanced-study-of-china-nasc": {
        "fellows": ["nasc-fellows-2526"],
        # The first five have no heading on the source page. Manoj Kewalramani
        # is listed there as "Programme Head, NASC Fellowship", so the group
        # reads as programme leadership -- that label is our inference, not
        # source text.
        "mentors": [
            ("nasc-leadership", None, 5),
            ("nasc-mentors", "Our Mentors", 4),
        ],
    },
}


# Mentors who are Takshashila staff already have a profile on the main site.
# Link those cards there rather than minting a duplicate record, so the merge
# into TakshashilaInst/takshashila doesn't create two of each person.
# Slugs taken from the live team page and verified to return 200; the rule is
# not simply lower+hyphen (note "Y. Nithiyanandam" -> "dr-y-nithiyanandam"),
# so re-verify with curl before adding to this map.
TEAM_PROFILE = "https://takshashila.org.in/content/team/{}.html"
PROFILES = {
    "Pranay Kotasthane": "pranay-kotasthane",
    "Manoj Kewalramani": "manoj-kewalramani",
    "Shambhavi Naik": "shambhavi-naik",
    "Y. Nithiyanandam": "dr-y-nithiyanandam",
    "Rijesh Panicker": "rijesh-panicker",
    "Lt General (Dr) Prakash Menon": "lt-general-dr-prakash-menon",
    "Aditya Ramanathan": "aditya-ramanathan",
    "Anand Arni": "anand-arni",
    "Narayan Ramachandran": "narayan-ramachandran",
}

# Typos in the published source copy. Kept explicit so a re-run doesn't
# silently reintroduce them, and so the diff against the source is auditable.
CORRECTIONS = {
    "Gvernment": "Government",
    "Sudent": "Student",
}


def apply_corrections(text: str) -> str:
    for wrong, right in CORRECTIONS.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)
    return text


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return apply_corrections(re.sub(r"\s+", " ", html.unescape(fragment)).strip())


def paragraphs(fragment: str) -> list[str]:
    parts = re.findall(r"<p[^>]*>(.*?)</p>", fragment, flags=re.S)
    if not parts:
        parts = [fragment]
    return [t for t in (strip_tags(p) for p in parts) if t]


def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[\s_]+", "-", name)


# Subordinate clauses that turn a role into a sentence. Cutting here keeps the
# role line readable instead of trailing off mid-thought.
TAIL_MARKERS = (
    ", where ", ", who ", ", whose ", ", with ", ", focusing ", ", and is ",
    " where he ", " where she ", " where they ", " with experience",
    " with a focus", " with research", " and is currently", " and has ",
)


def first_clause(bio: str, limit: int = 88) -> str:
    """Condense a paragraph bio into a role line for the .f-card .role slot."""
    # Drop the leading "Firstname is a/an/the ..." so the line reads as a role.
    text = re.sub(
        r"^(?:\S+\s+){1,3}?(?:is|was)\s+(?:currently|presently|now)?\s*(?:an|a|the)?\s*",
        "",
        bio,
        count=1,
    )
    text = re.sub(r"^(?:\S+\s+){1,3}?(?:holds|has|serves)\s+(?:an|a|the)?\s*", "", text, count=1)
    sentence = re.split(r"(?<=[.!?])\s", text)[0]

    lowered = sentence.lower()
    for marker in TAIL_MARKERS:
        position = lowered.find(marker)
        if position > 20:
            sentence = sentence[:position]
            lowered = sentence.lower()

    sentence = sentence.strip().rstrip(".,;: ")
    if len(sentence) > limit:
        # Prefer a clause boundary; fall back to a word boundary. Never cut a word.
        head = sentence[: limit + 1]
        for separator in (";", ","):
            if separator in head:
                candidate = head.rsplit(separator, 1)[0]
                if len(candidate) >= limit * 0.45:
                    sentence = candidate
                    break
        else:
            sentence = head.rsplit(" ", 1)[0]
        sentence = sentence.strip().rstrip(".,;: ")

    return sentence[:1].upper() + sentence[1:] if sentence else sentence


def trim_role(role: str, limit: int = 112) -> str:
    """Keep mentor role lines to a couple of lines so grid rows stay even.

    Their published roles append book credits and second affiliations after a
    semicolon; the leading appointment is the part the card needs.
    """
    role = role.strip().rstrip(".,;: ")
    if len(role) <= limit:
        return role
    if ";" in role:
        head = role.split(";", 1)[0].strip()
        if len(head) >= 24:
            return head.rstrip(".,;: ")
    head = role[: limit + 1]
    if "," in head:
        candidate = head.rsplit(",", 1)[0]
        if len(candidate) >= limit * 0.45:
            return candidate.rstrip(".,;: ")
    return head.rsplit(" ", 1)[0].rstrip(".,;: ")


def parse_fellows(page_html: str) -> list[list[dict]]:
    """Return one list of people per carousel block, in document order."""
    blocks = []
    for match in re.finditer(r'data-current-context="(.*?)"\s+data-', page_html, flags=re.S):
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        items = payload.get("userItems") or []
        if not items:
            continue
        people = []
        for item in items:
            name = (item.get("title") or "").strip()
            if not name:
                continue
            bio = strip_tags(item.get("description") or "")
            # Short entries are already a role line; long ones are prose to condense.
            subtitle = bio.rstrip(".,;: ") if len(bio) <= 100 else first_clause(bio)
            people.append(
                {
                    "name": name,
                    "subtitle": subtitle,
                    "bio": bio,
                    "asset": (item.get("image") or {}).get("assetUrl", ""),
                }
            )
        blocks.append(people)
    return blocks


def parse_mentors(page_html: str) -> list[dict]:
    """Walk image and text blocks in document order, pairing each image with the
    text block that follows it."""
    body = re.sub(r"<style[^>]*>.*?</style>", "", page_html, flags=re.S)
    body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S)
    # Remove carousel payloads so fellow photos don't leak into the mentor walk.
    body = re.sub(r'data-current-context="(.*?)"\s+data-', "", body, flags=re.S)

    events = []
    for match in re.finditer(
        r'<img[^>]*?(?:data-)?src="(https://images\.squarespace-cdn\.com/[^"?]+)', body
    ):
        events.append((match.start(), "img", match.group(1)))
    for match in re.finditer(
        r'<div class="sqs-html-content"[^>]*>(.*?)</div>\s*\n', body, flags=re.S
    ):
        paras = paragraphs(match.group(1))
        if paras:
            events.append((match.start(), "txt", paras))
    events.sort(key=lambda e: e[0])

    # Collapse the srcset duplicates Squarespace emits for each image.
    collapsed = []
    for _, kind, value in events:
        if collapsed and collapsed[-1] == (kind, value):
            continue
        collapsed.append((kind, value))

    people = []
    for index, (kind, value) in enumerate(collapsed):
        if kind != "img":
            continue
        following = collapsed[index + 1] if index + 1 < len(collapsed) else None
        if not following or following[0] != "txt":
            people.append({"name": None, "asset": value, "heading": None})
            continue
        paras = following[1]
        heading = paras[0] if len(paras) == 1 else None
        if heading:
            people.append({"name": None, "asset": value, "heading": None})
            continue
        interests = ""
        role_parts = []
        for para in paras[1:]:
            if para.lower().startswith("interest areas"):
                interests = para.split(":", 1)[-1].strip()
            else:
                role_parts.append(para)
        people.append(
            {
                "name": paras[0].rstrip(",; "),
                "subtitle": trim_role(", ".join(role_parts)),
                "interests": interests,
                "asset": value,
                "heading": _preceding_heading(collapsed, index),
            }
        )
    return [p for p in people if p.get("name")]


def _preceding_heading(collapsed, index):
    """Nearest single-paragraph text block before this image."""
    for kind, value in reversed(collapsed[:index]):
        if kind == "txt" and len(value) == 1 and len(value[0]) < 60:
            return value[0]
    return None


def yaml_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def emit_block(group: str, people: list[dict]) -> str:
    lines = []
    for person in people:
        lines.append(f"      - title: {yaml_quote(person['name'])}")
        if person.get("subtitle"):
            lines.append(f"        subtitle: {yaml_quote(person['subtitle'])}")
        lines.append(f"        image: {person['slug']}{person.get('ext', '.webp')}")
        lines.append(f"        path: {yaml_quote(person.get('path', '#'))}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-dir", required=True, type=pathlib.Path)
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--ext-map",
        type=pathlib.Path,
        help="Optional TSV of '<dest-without-extension>\\t<.ext>'. The download step "
        "fetches each photo as both WebP and JPEG and keeps the smaller; pass the "
        "resulting map here so the emitted YAML points at the file that survived.",
    )
    args = parser.parse_args()

    ext_map: dict[str, str] = {}
    if args.ext_map and args.ext_map.exists():
        for line in args.ext_map.read_text().splitlines():
            if "\t" in line:
                dest, ext = line.split("\t", 1)
                ext_map[dest.strip()] = ext.strip()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "blocks").mkdir(exist_ok=True)

    record: dict[str, list[dict]] = {}
    image_rows: list[tuple[str, str]] = []

    for slug, config in PAGES.items():
        path = args.html_dir / f"{slug}.html"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 1
        page_html = path.read_text(encoding="utf-8", errors="replace")

        carousels = parse_fellows(page_html)
        for group, people in zip(config["fellows"], carousels):
            record[group] = people

        mentors = parse_mentors(page_html)
        cursor = 0
        for group, heading, count in config["mentors"]:
            if heading is not None:
                for offset in range(cursor, len(mentors)):
                    if mentors[offset].get("heading") == heading:
                        cursor = offset
                        break
            record[group] = mentors[cursor : cursor + count]
            cursor += count

    for group, people in record.items():
        seen: dict[str, int] = {}
        for person in people:
            base = slugify(person["name"])
            seen[base] = seen.get(base, 0) + 1
            person["slug"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
            stem = f"assets/images/nasx/people/{group}/{person['slug']}"
            person["ext"] = ext_map.get(stem, ".webp")
            if person["name"] in PROFILES:
                person["path"] = TEAM_PROFILE.format(PROFILES[person["name"]])
            if person.get("asset"):
                image_rows.append((f"{stem}.webp", person["asset"]))
        (args.out_dir / "blocks" / f"{group}.yml").write_text(emit_block(group, people))

    (args.out_dir / "images.tsv").write_text(
        "".join(f"{dest}\t{url}\n" for dest, url in image_rows)
    )

    # Full record, including the bios no card renders today -- they are the
    # expensive part to re-fetch if the source pages ever come down.
    (args.out_dir / "nasx-people.json").write_text(json.dumps(record, indent=2))

    total = sum(len(v) for v in record.values())
    for group, people in record.items():
        missing = sum(1 for p in people if not p.get("asset"))
        note = f"  ({missing} without photo)" if missing else ""
        print(f"{group:26} {len(people):3d}{note}")
    print(f"{'TOTAL':26} {total:3d} people, {len(image_rows)} photos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
