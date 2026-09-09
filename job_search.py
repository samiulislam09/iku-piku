import os
import json
import re
import html
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = "seen_jobs.json"

MAX_JOBS_TO_SEND = 10
MAX_JOB_AGE_DAYS = 14


# ============================================================
# YOUR PROFILE
# ============================================================

PROFILE = {
    "primary": [
        "machine learning",
        "machine-learning",
        "ml engineer",
        "machine learning engineer",
        "llm",
        "large language model",
        "generative ai",
        "genai",
        "ai engineer",
        "ai developer",
        "nlp",
        "natural language processing",
        "voice ai",
    ],

    "backend": [
        "node.js",
        "nodejs",
        "node js",
        "express",
        "nestjs",
        "typescript",
        "rest api",
        "backend",
        "backend engineer",
    ],

    "frontend": [
        "next.js",
        "nextjs",
        "next js",
        "react",
        "react.js",
        "reactjs",
        "tailwind",
        "javascript",
    ],

    "mobile": [
        "react native",
        "react-native",
        "mobile developer",
        "mobile engineer",
    ],

    "general": [
        "full stack",
        "full-stack",
        "software engineer",
        "software developer",
        "web developer",
        "frontend engineer",
        "backend developer",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    # AI / ML / LLM
    '"AI Engineer" Bangladesh remote job',
    '"Machine Learning Engineer" Bangladesh remote job',
    '"LLM Engineer" Bangladesh remote job',
    '"Generative AI" Bangladesh remote job',
    '"NLP Engineer" Bangladesh remote job',
    '"AI Developer" Bangladesh remote job',

    # Node / Next / React
    '"Node.js" Bangladesh remote job',
    '"Node.js" Bangladesh remote developer',
    '"Next.js" Bangladesh remote job',
    '"React" Bangladesh remote job',
    '"React Native" Bangladesh remote job',

    # Full stack
    '"Full Stack Developer" Bangladesh remote',
    '"Full Stack Engineer" Bangladesh remote',
    '"Software Engineer" Bangladesh remote',

    # Explicit remote
    '"remote" "Bangladesh" "Node.js" job',
    '"remote" "Bangladesh" "Next.js" job',
    '"remote" "Bangladesh" "React" job',
    '"remote" "Bangladesh" "LLM" job',

    # Bangladesh job boards
    'site:bdjobs.com "remote" "software" Bangladesh',
    'site:bdjobs.com "remote" "developer" Bangladesh',
    'site:bdjobs.com "Node.js" "React"',
    'site:bdjobs.com "Next.js" "Node.js"',

    # LinkedIn indexed jobs
    'site:linkedin.com/jobs "Bangladesh" "Node.js" remote',
    'site:linkedin.com/jobs "Bangladesh" "Next.js" remote',
    'site:linkedin.com/jobs "Bangladesh" "AI Engineer" remote',

    # Company career pages
    '"Bangladesh" "Remote" "Next.js" careers',
    '"Bangladesh" "Remote" "Node.js" careers',
    '"Bangladesh" "Remote" "AI Engineer" careers',
]


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/139 Safari/537.36"
    )
})


# ============================================================
# LOAD / SAVE SEEN JOBS
# ============================================================

def load_seen_jobs():
    if not os.path.exists(SEEN_FILE):
        return {}

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen_jobs(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


# ============================================================
# HELPERS
# ============================================================

def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def clean_text(text):
    text = BeautifulSoup(text or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def job_id(title, url):
    value = f"{title}|{url}".lower()
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def escape_telegram_html(text):
    return (
        html.escape(str(text))
        .replace("&quot;", '"')
    )


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def build_google_news_url(query):
    encoded = quote_plus(f"{query} when:{MAX_JOB_AGE_DAYS}d")

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )


def search_google_news(query):
    url = build_google_news_url(query)

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        jobs = []

        for entry in feed.entries:
            title = clean_text(entry.get("title", ""))
            link = entry.get("link", "")
            description = clean_text(entry.get("summary", ""))

            published = entry.get("published", "")

            jobs.append({
                "title": title,
                "url": link,
                "description": description,
                "published": published,
                "source_query": query,
            })

        return jobs

    except Exception as e:
        print(f"Search failed: {query}")
        print(e)
        return []


# ============================================================
# EXTRACT SOURCE / COMPANY
# ============================================================

def extract_source(job):
    title = job["title"]

    if " - " in title:
        parts = title.split(" - ")

        if len(parts) >= 2:
            return parts[-1].strip()

    return "Unknown source"


def extract_company(job):
    title = job["title"]

    parts = title.split(" - ")

    if len(parts) >= 3:
        return parts[-2].strip()

    return extract_source(job)


# ============================================================
# JOB SCORING
# ============================================================

def contains_any(text, keywords):
    text = normalize(text)

    return any(keyword.lower() in text for keyword in keywords)


def score_job(job):
    title = normalize(job["title"])
    description = normalize(job["description"])

    text = f"{title} {description}"

    score = 0
    matched = []
    missing = []

    # --------------------------------------------------------
    # Bangladesh eligibility
    # --------------------------------------------------------

    bangladesh_terms = [
        "bangladesh",
        "dhaka",
        "bd",
        "anywhere in bangladesh",
        "remote - bangladesh",
        "remote, bangladesh",
    ]

    worldwide_terms = [
        "worldwide",
        "work from anywhere",
        "anywhere in the world",
        "global remote",
        "remote anywhere",
        "remote - worldwide",
    ]

    asia_terms = [
        "asia",
        "asia pacific",
        "apac",
        "south asia",
    ]

    us_only = [
        "us only",
        "usa only",
        "united states only",
        "must be located in the us",
        "must be authorized to work in the us",
    ]

    europe_only = [
        "europe only",
        "eu only",
        "uk only",
    ]

    if contains_any(text, bangladesh_terms):
        score += 20

    elif contains_any(text, worldwide_terms):
        score += 20

    elif contains_any(text, asia_terms):
        score += 15

    if contains_any(text, us_only):
        score -= 40

    if contains_any(text, europe_only):
        score -= 30

    # --------------------------------------------------------
    # Remote
    # --------------------------------------------------------

    remote_terms = [
        "remote",
        "work from home",
        "distributed",
        "remote-first",
        "remote first",
    ]

    if contains_any(text, remote_terms):
        score += 20
    else:
        score -= 40

    # --------------------------------------------------------
    # Primary AI / ML skills
    # --------------------------------------------------------

    for keyword in PROFILE["primary"]:
        if keyword.lower() in text:
            score += 8
            matched.append(keyword)

    # --------------------------------------------------------
    # Backend
    # --------------------------------------------------------

    backend_count = 0

    for keyword in PROFILE["backend"]:
        if keyword.lower() in text:
            backend_count += 1
            matched.append(keyword)

    score += min(backend_count * 4, 16)

    # --------------------------------------------------------
    # Frontend
    # --------------------------------------------------------

    frontend_count = 0

    for keyword in PROFILE["frontend"]:
        if keyword.lower() in text:
            frontend_count += 1
            matched.append(keyword)

    score += min(frontend_count * 4, 16)

    # --------------------------------------------------------
    # Mobile
    # --------------------------------------------------------

    for keyword in PROFILE["mobile"]:
        if keyword.lower() in text:
            score += 5
            matched.append(keyword)

    # --------------------------------------------------------
    # General software engineering
    # --------------------------------------------------------

    for keyword in PROFILE["general"]:
        if keyword.lower() in title:
            score += 4

    # --------------------------------------------------------
    # Negative signals
    # --------------------------------------------------------

    negative = [
        "internship",
        "intern",
        "unpaid",
        "volunteer",
        "senior director",
        "staff engineer",
        "principal engineer",
        "10+ years",
        "8+ years",
        "7+ years",
    ]

    for keyword in negative:
        if keyword in text:
            score -= 10

    # --------------------------------------------------------
    # Experience
    # --------------------------------------------------------

    experience_patterns = [
        r"(\d+)\+?\s*years",
        r"(\d+)\s*-\s*(\d+)\s*years",
    ]

    for pattern in experience_patterns:
        matches = re.findall(pattern, text)

        for match in matches:

            if isinstance(match, tuple):
                numbers = [int(x) for x in match if x.isdigit()]

                if numbers:
                    max_year = max(numbers)

                    if max_year <= 5:
                        score += 5

                    elif max_year >= 7:
                        score -= 8

            else:
                years = int(match)

                if years <= 5:
                    score += 5

                elif years >= 7:
                    score -= 8

    # --------------------------------------------------------
    # Missing / useful skills
    # --------------------------------------------------------

    important_skills = [
        "python",
        "aws",
        "docker",
        "postgresql",
        "mongodb",
        "redis",
        "typescript",
        "next.js",
        "node.js",
        "react",
        "react native",
        "llm",
        "machine learning",
    ]

    for skill in important_skills:
        if skill in text:
            if skill not in matched:
                matched.append(skill)

    # Remove duplicates
    matched = list(dict.fromkeys(matched))

    # Clamp score
    score = max(0, min(score, 100))

    if score >= 85:
        recommendation = "🔥 Excellent match"

    elif score >= 70:
        recommendation = "🟢 Strong match"

    elif score >= 55:
        recommendation = "🟡 Possible match"

    else:
        recommendation = "⚪ Weak match"

    return {
        "score": score,
        "matched": matched[:12],
        "recommendation": recommendation,
    }


# ============================================================
# FILTER JOBS
# ============================================================

def is_relevant(job):
    title = normalize(job["title"])
    description = normalize(job["description"])

    text = f"{title} {description}"

    # Reject clearly non-job content
    bad_terms = [
        "course",
        "tutorial",
        "salary guide",
        "career guide",
        "how to become",
        "resume tips",
        "interview tips",
    ]

    if contains_any(text, bad_terms):
        return False

    # Must contain some software/AI relevance
    relevant_terms = []

    for category in PROFILE.values():
        relevant_terms.extend(category)

    if not contains_any(text, relevant_terms):
        return False

    # Must have remote indication
    remote_terms = [
        "remote",
        "work from home",
        "distributed",
        "remote-first",
        "remote first",
    ]

    if not contains_any(text, remote_terms):
        return False

    return True


# ============================================================
# DEDUPLICATE
# ============================================================

def deduplicate_jobs(jobs):
    unique = {}
    seen_titles = set()

    for job in jobs:

        jid = job_id(job["title"], job["url"])

        normalized_title = normalize(job["title"])

        if jid in unique:
            continue

        # Prevent Google News from returning nearly identical results
        title_key = re.sub(r"[^a-z0-9]+", " ", normalized_title)

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)
        unique[jid] = job

    return list(unique.values())


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = session.post(
        url,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()


# ============================================================
# FORMAT JOB
# ============================================================

def format_job(job, rank):

    score = job["score"]
    title = escape_telegram_html(job["title"])
    company = escape_telegram_html(job["company"])
    source = escape_telegram_html(job["source"])

    matched = job["matched"]

    if matched:
        skills = ", ".join(
            escape_telegram_html(x)
            for x in matched[:8]
        )
    else:
        skills = "General software engineering"

    published = escape_telegram_html(
        job.get("published", "Unknown")
    )

    url = html.escape(job["url"], quote=True)

    return f"""
<b>{rank}. {title}</b>

🏢 <b>Company:</b> {company}
📊 <b>Match:</b> {score}%
🎯 <b>{job["recommendation"]}</b>
🌍 <b>Remote:</b> Yes
📅 <b>Discovered:</b> {published}

🧠 <b>Matching skills:</b>
{skills}

🔗 <a href="{url}">Apply / View Job</a>

━━━━━━━━━━━━━━━━━━━━
"""


# ============================================================
# MAIN
# ============================================================

def main():

    print("====================================")
    print("Remote Job Finder")
    print("====================================")

    seen = load_seen_jobs()

    all_jobs = []

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    for index, query in enumerate(SEARCH_QUERIES, start=1):

        print(
            f"[{index}/{len(SEARCH_QUERIES)}] "
            f"Searching: {query}"
        )

        jobs = search_google_news(query)

        print(f"   Found: {len(jobs)}")

        all_jobs.extend(jobs)

    print()
    print(f"Total raw jobs: {len(all_jobs)}")

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    all_jobs = deduplicate_jobs(all_jobs)

    print(f"After deduplication: {len(all_jobs)}")

    # --------------------------------------------------------
    # Filter
    # --------------------------------------------------------

    relevant_jobs = []

    for job in all_jobs:

        if not is_relevant(job):
            continue

        jid = job_id(
            job["title"],
            job["url"]
        )

        # Already sent
        if jid in seen:
            continue

        scoring = score_job(job)

        if scoring["score"] < 45:
            continue

        job["score"] = scoring["score"]
        job["matched"] = scoring["matched"]
        job["recommendation"] = scoring["recommendation"]

        job["company"] = extract_company(job)
        job["source"] = extract_source(job)

        relevant_jobs.append(job)

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    relevant_jobs.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    relevant_jobs = relevant_jobs[:MAX_JOBS_TO_SEND]

    print(
        f"Relevant new jobs: "
        f"{len(relevant_jobs)}"
    )

    # --------------------------------------------------------
    # Telegram message
    # --------------------------------------------------------

    today = datetime.now().strftime("%d %B %Y")

    if not relevant_jobs:

        message = f"""
<b>🔎 DAILY BANGLADESH REMOTE JOB ALERT</b>

📅 {today}

No new high-quality remote jobs found today.

I'll search again tomorrow.
"""

        send_telegram(message)

    else:

        header = f"""
<b>🚀 DAILY REMOTE JOB ALERT</b>

📅 {today}

🇧🇩 <b>Location:</b> Bangladesh
💻 <b>Profile:</b> AI/ML • LLM • Node.js • Next.js • React • React Native

🔥 <b>{len(relevant_jobs)} new relevant jobs found</b>

━━━━━━━━━━━━━━━━━━━━
"""

        send_telegram(header)

        for index, job in enumerate(
            relevant_jobs,
            start=1
        ):

            message = format_job(
                job,
                index
            )

            send_telegram(message)

            # Mark as seen
            jid = job_id(
                job["title"],
                job["url"]
            )

            seen[jid] = {
                "title": job["title"],
                "url": job["url"],
                "sent_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

    # --------------------------------------------------------
    # Cleanup old seen jobs
    # --------------------------------------------------------

    cutoff = datetime.now(
        timezone.utc
    ) - timedelta(days=60)

    cleaned_seen = {}

    for jid, data in seen.items():

        try:
            sent_at = datetime.fromisoformat(
                data["sent_at"]
            )

            if sent_at >= cutoff:
                cleaned_seen[jid] = data

        except Exception:
            cleaned_seen[jid] = data

    save_seen_jobs(cleaned_seen)

    print()
    print("Done.")


if __name__ == "__main__":
    main()