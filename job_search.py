import os
import re
import json
import time
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = "seen_jobs.json"

MAX_JOBS_TO_SEND = 15
MAX_JOB_AGE_DAYS = 14
SEEN_JOB_RETENTION_DAYS = 60

REQUEST_TIMEOUT = 25
REQUEST_DELAY = 1.0


# ============================================================
# YOUR JOB PROFILE
# ============================================================

PROFILE = {
    # Highest priority
    "ai": [
        "machine learning",
        "machine-learning",
        "machine learning engineer",
        "ml engineer",
        "artificial intelligence",
        "artificial intelligence engineer",
        "ai engineer",
        "ai developer",
        "ai software engineer",
        "generative ai",
        "genai",
        "llm",
        "llm engineer",
        "llm developer",
        "large language model",
        "large language models",
        "nlp",
        "nlp engineer",
        "natural language processing",
        "voice ai",
        "voice agent",
        "conversational ai",
    ],

    # Strong priority
    "backend": [
        "node.js",
        "nodejs",
        "node js",
        "express.js",
        "expressjs",
        "express",
        "nestjs",
        "nest.js",
        "typescript",
        "javascript",
        "backend engineer",
        "backend developer",
        "backend development",
        "rest api",
        "restful api",
        "api development",
    ],

    # Strong priority
    "frontend": [
        "next.js",
        "nextjs",
        "next js",
        "react.js",
        "reactjs",
        "react js",
        "react",
        "frontend engineer",
        "frontend developer",
        "front-end engineer",
        "front-end developer",
        "tailwind",
    ],

    # Strong priority
    "mobile": [
        "react native",
        "react-native",
        "react native developer",
        "react native engineer",
        "mobile developer",
        "mobile engineer",
    ],

    # General roles
    "general": [
        "full stack",
        "full-stack",
        "fullstack",
        "full stack engineer",
        "full stack developer",
        "software engineer",
        "software developer",
        "web developer",
        "web engineer",
    ],

    # Helpful secondary skills
    "secondary": [
        "postgresql",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "docker",
        "aws",
        "azure",
        "gcp",
        "microservices",
        "graphql",
        "prisma",
        "sql",
        "git",
        "github",
        "ci/cd",
        "testing",
        "jest",
        "playwright",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [

    # --------------------------------------------------------
    # LINKEDIN
    # --------------------------------------------------------

    'site:linkedin.com/jobs/view Bangladesh remote "Node.js"',
    'site:linkedin.com/jobs/view Bangladesh remote "NodeJS"',
    'site:linkedin.com/jobs/view Bangladesh remote "Next.js"',
    'site:linkedin.com/jobs/view Bangladesh remote "React"',
    'site:linkedin.com/jobs/view Bangladesh remote "React Native"',
    'site:linkedin.com/jobs/view Bangladesh remote "AI Engineer"',
    'site:linkedin.com/jobs/view Bangladesh remote "Machine Learning"',
    'site:linkedin.com/jobs/view Bangladesh remote "LLM"',
    'site:linkedin.com/jobs/view Bangladesh remote "Generative AI"',
    'site:linkedin.com/jobs/view Bangladesh remote "Full Stack Developer"',
    'site:linkedin.com/jobs/view Bangladesh remote "Software Engineer"',

    # --------------------------------------------------------
    # FACEBOOK
    # --------------------------------------------------------

    'site:facebook.com Bangladesh remote job "Node.js"',
    'site:facebook.com Bangladesh remote job "Next.js"',
    'site:facebook.com Bangladesh remote job "React"',
    'site:facebook.com Bangladesh remote job "React Native"',
    'site:facebook.com Bangladesh remote job "AI Engineer"',
    'site:facebook.com Bangladesh remote job "Machine Learning"',
    'site:facebook.com Bangladesh remote job "LLM"',
    'site:facebook.com Bangladesh remote job "Full Stack Developer"',
    'site:facebook.com Bangladesh remote job "Software Engineer"',

    # Facebook groups/pages
    'site:facebook.com/groups Bangladesh remote developer job',
    'site:facebook.com/groups Bangladesh software engineer job',
    'site:facebook.com/groups Bangladesh programming jobs',
    'site:facebook.com/groups Bangladesh remote jobs',

    # --------------------------------------------------------
    # BDJOBS
    # --------------------------------------------------------

    'site:bdjobs.com Bangladesh remote "Node.js"',
    'site:bdjobs.com Bangladesh remote "Next.js"',
    'site:bdjobs.com Bangladesh remote "React"',
    'site:bdjobs.com Bangladesh remote "React Native"',
    'site:bdjobs.com Bangladesh remote "AI"',
    'site:bdjobs.com Bangladesh remote "Machine Learning"',
    'site:bdjobs.com Bangladesh remote "Full Stack"',
    'site:bdjobs.com Bangladesh remote "Software Engineer"',

    # --------------------------------------------------------
    # GENERAL WEB
    # --------------------------------------------------------

    '"Node.js" "remote" "Bangladesh" job',
    '"NodeJS" "remote" "Bangladesh" job',
    '"Next.js" "remote" "Bangladesh" job',
    '"React" "remote" "Bangladesh" job',
    '"React Native" "remote" "Bangladesh" job',
    '"AI Engineer" "remote" "Bangladesh" job',
    '"Machine Learning Engineer" "remote" "Bangladesh" job',
    '"LLM Engineer" "remote" "Bangladesh" job',
    '"Generative AI" "remote" "Bangladesh" job',
    '"Full Stack Developer" "remote" "Bangladesh" job',
    '"Software Engineer" "remote" "Bangladesh" job',

    # --------------------------------------------------------
    # WORLDWIDE / ASIA REMOTE
    # --------------------------------------------------------

    '"Node.js" "remote" "worldwide" job',
    '"Next.js" "remote" "worldwide" job',
    '"React" "remote" "worldwide" job',
    '"LLM" "remote" "worldwide" job',
    '"AI Engineer" "remote" "worldwide" job',

    '"Node.js" "remote" "Asia" job',
    '"Next.js" "remote" "Asia" job',
    '"React" "remote" "Asia" job',
    '"AI Engineer" "remote" "Asia" job',
    '"LLM" "remote" "Asia" job',

    # --------------------------------------------------------
    # CAREER PAGES
    # --------------------------------------------------------

    '"Bangladesh" "remote" "Node.js" careers',
    '"Bangladesh" "remote" "Next.js" careers',
    '"Bangladesh" "remote" "React" careers',
    '"Bangladesh" "remote" "AI Engineer" careers',
    '"Bangladesh" "remote" "LLM" careers',
    '"Bangladesh" "remote" "Software Engineer" careers',
]


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = BeautifulSoup(
        str(value),
        "html.parser"
    ).get_text(" ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize(value):
    return clean_text(value).lower()


def contains(text, keyword):
    return keyword.lower() in text


def contains_any(text, keywords):
    return any(
        keyword.lower() in text
        for keyword in keywords
    )


def unique_list(values):
    return list(dict.fromkeys(values))


# ============================================================
# JOB ID
# ============================================================

def make_job_id(title, url):
    raw = (
        f"{normalize(title)}|"
        f"{normalize(url)}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


# ============================================================
# SEEN JOBS
# ============================================================

def load_seen_jobs():

    if not os.path.exists(SEEN_FILE):
        return {}

    try:
        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception as error:

        print(
            f"Could not load {SEEN_FILE}: {error}"
        )

        return {}


def save_seen_jobs(seen):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            seen,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# SOURCE DETECTION
# ============================================================

def detect_source(url):

    hostname = urlparse(url).netloc.lower()

    if "linkedin.com" in hostname:
        return "LinkedIn"

    if "facebook.com" in hostname:
        return "Facebook"

    if "bdjobs.com" in hostname:
        return "Bdjobs"

    if "indeed.com" in hostname:
        return "Indeed"

    if "wellfound.com" in hostname:
        return "Wellfound"

    if "remoteok.com" in hostname:
        return "RemoteOK"

    if "weworkremotely.com" in hostname:
        return "We Work Remotely"

    if "glassdoor.com" in hostname:
        return "Glassdoor"

    return hostname.replace("www.", "")


# ============================================================
# GOOGLE NEWS RSS SEARCH
# ============================================================

def google_news_search(query):

    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        f"&hl=en-US"
        f"&gl=US"
        f"&ceid=US:en"
    )

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        jobs = []

        for entry in feed.entries:

            title = clean_text(
                entry.get("title", "")
            )

            link = entry.get(
                "link",
                ""
            )

            summary = clean_text(
                entry.get(
                    "summary",
                    ""
                )
            )

            published = entry.get(
                "published",
                ""
            )

            if not title or not link:
                continue

            jobs.append({
                "title": title,
                "url": link,
                "description": summary,
                "published": published,
                "source": detect_source(link),
                "search_query": query,
            })

        return jobs

    except Exception as error:

        print(
            f"Google News error: {error}"
        )

        return []


# ============================================================
# DUCKDUCKGO HTML SEARCH
# ============================================================

def duckduckgo_search(query):

    url = (
        "https://html.duckduckgo.com/html/"
        f"?q={quote_plus(query)}"
    )

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        jobs = []

        results = soup.select(
            ".result"
        )

        for result in results:

            link_element = result.select_one(
                ".result__a"
            )

            if not link_element:
                continue

            title = clean_text(
                link_element.get_text()
            )

            href = link_element.get(
                "href",
                ""
            )

            snippet_element = result.select_one(
                ".result__snippet"
            )

            description = ""

            if snippet_element:
                description = clean_text(
                    snippet_element.get_text()
                )

            if not href:
                continue

            jobs.append({
                "title": title,
                "url": href,
                "description": description,
                "published": "",
                "source": detect_source(href),
                "search_query": query,
            })

        return jobs

    except Exception as error:

        print(
            f"DuckDuckGo error: {error}"
        )

        return []


# ============================================================
# SEARCH ALL SOURCES
# ============================================================

def search_all():

    all_jobs = []

    total = len(SEARCH_QUERIES)

    for index, query in enumerate(
        SEARCH_QUERIES,
        start=1
    ):

        print(
            f"[{index}/{total}] {query}"
        )

        google_jobs = google_news_search(
            query
        )

        all_jobs.extend(
            google_jobs
        )

        time.sleep(
            REQUEST_DELAY
        )

        duck_jobs = duckduckgo_search(
            query
        )

        all_jobs.extend(
            duck_jobs
        )

        time.sleep(
            REQUEST_DELAY
        )

    return all_jobs


# ============================================================
# URL CLEANING
# ============================================================

def clean_url(url):

    if not url:
        return ""

    # Google News redirect
    if "news.google.com" in url:

        try:

            parsed = urlparse(url)

            # feedparser normally provides the actual URL,
            # but keep this fallback.
            if parsed.query:
                return url

        except Exception:
            pass

    return url


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):

    title = clean_text(title)

    # Remove common search-result suffixes
    separators = [
        " - LinkedIn",
        " | LinkedIn",
        " - Facebook",
        " | Facebook",
        " - Bdjobs",
        " | Bdjobs",
    ]

    for separator in separators:

        if separator.lower() in title.lower():

            title = re.split(
                re.escape(separator),
                title,
                flags=re.IGNORECASE
            )[0]

    return title.strip()


# ============================================================
# EXTRACT COMPANY
# ============================================================

def extract_company(job):

    title = job["title"]

    source = job["source"]

    # Common:
    # Job Title - Company - LinkedIn
    parts = [
        part.strip()
        for part in title.split(" - ")
        if part.strip()
    ]

    if len(parts) >= 3:

        return parts[-2]

    if len(parts) == 2:

        if source not in parts[-1]:
            return parts[-1]

    # Try description
    description = job["description"]

    company_patterns = [
        r"at ([A-Z][A-Za-z0-9 .&_-]{2,50})",
        r"company[:\s]+([A-Z][A-Za-z0-9 .&_-]{2,50})",
    ]

    for pattern in company_patterns:

        match = re.search(
            pattern,
            description,
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return "Unknown company"


# ============================================================
# LOCATION / REMOTE ELIGIBILITY
# ============================================================

BANGLADESH_TERMS = [
    "bangladesh",
    "dhaka",
    "chittagong",
    "chattogram",
    "sylhet",
    "rangpur",
    "rajshahi",
    "khulna",
    "barisal",
    "mymensingh",
]

WORLDWIDE_TERMS = [
    "worldwide",
    "work from anywhere",
    "anywhere in the world",
    "global remote",
    "remote worldwide",
    "remote anywhere",
    "distributed worldwide",
    "anywhere",
]

ASIA_TERMS = [
    "asia",
    "asia pacific",
    "asia-pacific",
    "apac",
    "south asia",
    "southeast asia",
]

REMOTE_TERMS = [
    "remote",
    "work from home",
    "work remotely",
    "distributed",
    "remote-first",
    "remote first",
    "fully remote",
]

US_ONLY_TERMS = [
    "us only",
    "usa only",
    "u.s. only",
    "united states only",
    "remote us only",
    "remote usa only",
    "must be located in the us",
    "must be located in the usa",
    "must reside in the us",
    "must reside in the usa",
]

EU_ONLY_TERMS = [
    "europe only",
    "eu only",
    "uk only",
    "must be located in europe",
    "must reside in europe",
]


def determine_remote_eligibility(text):

    if contains_any(
        text,
        US_ONLY_TERMS
    ):
        return False, "US only"

    if contains_any(
        text,
        EU_ONLY_TERMS
    ):
        return False, "Europe only"

    if contains_any(
        text,
        BANGLADESH_TERMS
    ):
        return True, "Bangladesh"

    if contains_any(
        text,
        WORLDWIDE_TERMS
    ):
        return True, "Worldwide"

    if contains_any(
        text,
        ASIA_TERMS
    ):
        return True, "Asia/APAC"

    # Generic remote job without location.
    # Keep it as "possible", but score lower.
    if contains_any(
        text,
        REMOTE_TERMS
    ):
        return True, "Remote - location unclear"

    return False, "Not remote"


# ============================================================
# EXPERIENCE
# ============================================================

def experience_score(text):

    score = 0
    reasons = []

    # Explicit ranges:
    # 1-3 years
    # 2 - 5 years
    range_pattern = re.compile(
        r"(\d+)\s*[-–]\s*(\d+)\s*years?",
        re.IGNORECASE
    )

    for match in range_pattern.finditer(text):

        low = int(match.group(1))
        high = int(match.group(2))

        if low <= 2 and high <= 5:

            score += 8
            reasons.append(
                f"{low}-{high} years experience"
            )

        elif low <= 3 and high <= 6:

            score += 4

    # X+ years
    plus_pattern = re.compile(
        r"(\d+)\+?\s*years?\s*(?:of)?\s*experience",
        re.IGNORECASE
    )

    for match in plus_pattern.finditer(text):

        years = int(
            match.group(1)
        )

        if years <= 5:

            score += 8

            reasons.append(
                f"{years}+ years experience"
            )

        elif years >= 7:

            score -= 10

    return score, reasons


# ============================================================
# SKILL MATCHING
# ============================================================

def skill_matches(text):

    matched = {
        "ai": [],
        "backend": [],
        "frontend": [],
        "mobile": [],
        "general": [],
        "secondary": [],
    }

    for category, skills in PROFILE.items():

        for skill in skills:

            if skill.lower() in text:

                matched[category].append(
                    skill
                )

    return matched


# ============================================================
# JOB RELEVANCE
# ============================================================

def is_obviously_not_a_job(text):

    negative = [
        "course",
        "courses",
        "tutorial",
        "tutorials",
        "salary guide",
        "career guide",
        "career advice",
        "resume tips",
        "cv tips",
        "interview tips",
        "how to become",
        "training program",
        "bootcamp",
        "webinar",
    ]

    return contains_any(
        text,
        negative
    )


def is_remote(text):

    return contains_any(
        text,
        REMOTE_TERMS
    )


def is_relevant_job(job):

    title = normalize(
        job["title"]
    )

    description = normalize(
        job["description"]
    )

    text = (
        f"{title} "
        f"{description}"
    )

    if is_obviously_not_a_job(text):

        return False

    # Must have remote indication
    if not is_remote(text):

        return False

    all_skills = []

    for skills in PROFILE.values():

        all_skills.extend(
            skills
        )

    # Must match at least one relevant
    # technology / job type.
    if not contains_any(
        text,
        all_skills
    ):

        return False

    # Reject obvious unrelated jobs
    unrelated = [
        "sales manager",
        "sales representative",
        "accountant",
        "hr manager",
        "human resources",
        "graphic designer",
        "video editor",
        "content writer",
        "customer support",
        "customer service representative",
        "digital marketer",
        "seo specialist",
    ]

    # Only reject if it appears strongly
    # in the title.
    if contains_any(
        title,
        unrelated
    ):

        return False

    return True


# ============================================================
# SCORE JOB
# ============================================================

def score_job(job):

    title = normalize(
        job["title"]
    )

    description = normalize(
        job["description"]
    )

    text = (
        f"{title} "
        f"{description}"
    )

    score = 0

    reasons = []

    # --------------------------------------------------------
    # Remote + Bangladesh
    # --------------------------------------------------------

    eligible, location_type = (
        determine_remote_eligibility(
            text
        )
    )

    if not eligible:

        return {
            "score": 0,
            "eligible": False,
            "location_type": location_type,
            "matched": [],
            "reasons": [],
        }

    if location_type == "Bangladesh":

        score += 30
        reasons.append(
            "Bangladesh eligible"
        )

    elif location_type == "Worldwide":

        score += 30
        reasons.append(
            "Worldwide remote"
        )

    elif location_type == "Asia/APAC":

        score += 25
        reasons.append(
            "Asia/APAC remote"
        )

    else:

        score += 12
        reasons.append(
            "Remote, location unclear"
        )

    # --------------------------------------------------------
    # AI / ML
    # --------------------------------------------------------

    matched = skill_matches(text)

    ai_count = len(
        matched["ai"]
    )

    if ai_count:

        ai_points = min(
            ai_count * 8,
            35
        )

        score += ai_points

        reasons.append(
            "AI/ML/LLM experience matches"
        )

    # --------------------------------------------------------
    # Backend
    # --------------------------------------------------------

    backend_count = len(
        matched["backend"]
    )

    if backend_count:

        backend_points = min(
            backend_count * 5,
            20
        )

        score += backend_points

        reasons.append(
            "Node.js/backend stack matches"
        )

    # --------------------------------------------------------
    # Frontend
    # --------------------------------------------------------

    frontend_count = len(
        matched["frontend"]
    )

    if frontend_count:

        frontend_points = min(
            frontend_count * 5,
            20
        )

        score += frontend_points

        reasons.append(
            "React/Next.js stack matches"
        )

    # --------------------------------------------------------
    # Mobile
    # --------------------------------------------------------

    mobile_count = len(
        matched["mobile"]
    )

    if mobile_count:

        score += min(
            mobile_count * 6,
            15
        )

        reasons.append(
            "React Native/mobile matches"
        )

    # --------------------------------------------------------
    # General role
    # --------------------------------------------------------

    general_count = len(
        matched["general"]
    )

    if general_count:

        score += min(
            general_count * 4,
            12
        )

    # --------------------------------------------------------
    # Secondary skills
    # --------------------------------------------------------

    secondary_count = len(
        matched["secondary"]
    )

    score += min(
        secondary_count * 2,
        10
    )

    # --------------------------------------------------------
    # Experience
    # --------------------------------------------------------

    experience_points, experience_reasons = (
        experience_score(text)
    )

    score += experience_points

    reasons.extend(
        experience_reasons
    )

    # --------------------------------------------------------
    # Negative signals
    # --------------------------------------------------------

    negative_signals = [
        "internship",
        "intern ",
        "unpaid",
        "volunteer",
        "principal engineer",
        "staff engineer",
        "director of engineering",
        "vp engineering",
        "vice president engineering",
        "10+ years",
        "9+ years",
        "8+ years",
        "7+ years",
    ]

    negative_hits = [
        x for x in negative_signals
        if x in text
    ]

    if negative_hits:

        score -= min(
            len(negative_hits) * 8,
            25
        )

    # --------------------------------------------------------
    # Seniority
    # --------------------------------------------------------

    senior_title_terms = [
        "senior software engineer",
        "senior developer",
        "senior engineer",
        "senior full stack",
        "senior full-stack",
        "lead engineer",
        "tech lead",
    ]

    if contains_any(
        title,
        senior_title_terms
    ):

        # You have some experience, so senior
        # roles aren't automatically rejected.
        score += 2

        reasons.append(
            "Senior-level role"
        )

    # --------------------------------------------------------
    # Job title bonus
    # --------------------------------------------------------

    title_bonus_terms = [
        "ai engineer",
        "machine learning engineer",
        "llm engineer",
        "ai developer",
        "full stack engineer",
        "full stack developer",
        "software engineer",
        "node.js developer",
        "nodejs developer",
        "next.js developer",
        "react developer",
        "react native developer",
    ]

    title_hits = [
        term
        for term in title_bonus_terms
        if term in title
    ]

    if title_hits:

        score += min(
            len(title_hits) * 6,
            12
        )

    # --------------------------------------------------------
    # Clamp
    # --------------------------------------------------------

    score = max(
        0,
        min(score, 100)
    )

    if score >= 85:

        recommendation = (
            "🔥 Excellent match"
        )

    elif score >= 70:

        recommendation = (
            "🟢 Strong match"
        )

    elif score >= 55:

        recommendation = (
            "🟡 Possible match"
        )

    else:

        recommendation = (
            "⚪ Weak match"
        )

    all_matched = []

    for category in matched.values():

        all_matched.extend(
            category
        )

    all_matched = unique_list(
        all_matched
    )

    return {
        "score": score,
        "eligible": True,
        "location_type": location_type,
        "matched": all_matched[:15],
        "reasons": unique_list(
            reasons
        )[:8],
        "recommendation": recommendation,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def normalize_title_for_duplicate(title):

    title = normalize(title)

    # Remove common source suffixes
    title = re.sub(
        r"\b(linkedin|facebook|bdjobs)\b",
        "",
        title
    )

    # Remove punctuation
    title = re.sub(
        r"[^a-z0-9]+",
        " ",
        title
    )

    return title.strip()


def deduplicate_jobs(jobs):

    unique = {}

    title_index = {}

    for job in jobs:

        title = clean_title(
            job["title"]
        )

        url = clean_url(
            job["url"]
        )

        if not title or not url:
            continue

        jid = make_job_id(
            title,
            url
        )

        if jid in unique:
            continue

        normalized_title = (
            normalize_title_for_duplicate(
                title
            )
        )

        # If exact same title already exists,
        # keep the first result.
        if normalized_title in title_index:

            existing_id = title_index[
                normalized_title
            ]

            existing = unique[
                existing_id
            ]

            # Prefer known source over
            # unknown source.
            if (
                existing["source"]
                in ["", "Unknown"]
                and job["source"]
                not in ["", "Unknown"]
            ):

                del unique[
                    existing_id
                ]

            else:

                continue

        job["title"] = title
        job["url"] = url
        job["id"] = jid

        unique[jid] = job
        title_index[
            normalized_title
        ] = jid

    return list(
        unique.values()
    )


# ============================================================
# TELEGRAM HELPERS
# ============================================================

def telegram_escape(text):

    if text is None:
        return ""

    # Telegram HTML parse mode
    text = str(text)

    text = (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return text


def telegram_send(message):

    endpoint = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = session.post(
        endpoint,
        json=payload,
        timeout=REQUEST_TIMEOUT
    )

    if not response.ok:

        print(
            "Telegram error:",
            response.text
        )

    response.raise_for_status()


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def format_job_message(
    job,
    rank
):

    title = telegram_escape(
        job["title"]
    )

    company = telegram_escape(
        job.get(
            "company",
            "Unknown company"
        )
    )

    source = telegram_escape(
        job.get(
            "source",
            "Unknown"
        )
    )

    score = job["score"]

    location = telegram_escape(
        job["location_type"]
    )

    recommendation = telegram_escape(
        job["recommendation"]
    )

    matched = job.get(
        "matched",
        []
    )

    reasons = job.get(
        "reasons",
        []
    )

    if matched:

        skill_text = "\n".join(
            f"✓ {telegram_escape(skill)}"
            for skill in matched[:8]
        )

    else:

        skill_text = "No specific skills detected"

    if reasons:

        reason_text = "\n".join(
            f"• {telegram_escape(reason)}"
            for reason in reasons[:5]
        )

    else:

        reason_text = "Strong general stack match"

    url = telegram_escape(
        job["url"]
    )

    published = telegram_escape(
        job.get(
            "published",
            ""
        )
    )

    published_line = ""

    if published:

        published_line = (
            f"📅 <b>Posted:</b> "
            f"{published}\n"
        )

    return f"""
<b>#{rank} — {title}</b>

🏢 <b>Company:</b> {company}
📊 <b>Match:</b> {score}%
🎯 <b>{recommendation}</b>
🌍 <b>Location:</b> {location}
📌 <b>Source:</b> {source}
{published_line}
🧠 <b>Matching skills</b>
{skill_text}

💡 <b>Why it matches</b>
{reason_text}

🔗 <a href="{url}">View / Apply</a>

━━━━━━━━━━━━━━━━━━━━
"""


# ============================================================
# TELEGRAM HEADER
# ============================================================

def send_header(jobs):

    today = datetime.now(
        timezone.utc
    ).strftime(
        "%d %B %Y"
    )

    excellent = sum(
        1
        for job in jobs
        if job["score"] >= 85
    )

    strong = sum(
        1
        for job in jobs
        if 70 <= job["score"] < 85
    )

    message = f"""
<b>🚀 DAILY REMOTE JOB ALERT</b>

📅 {today}

🇧🇩 <b>Target:</b> Bangladesh
💻 <b>Profile:</b>
AI/ML • LLM • Node.js • Next.js • React • React Native

🔥 <b>{len(jobs)} new jobs found</b>

🏆 Excellent: {excellent}
🟢 Strong: {strong}

━━━━━━━━━━━━━━━━━━━━
"""

    telegram_send(
        message
    )


# ============================================================
# NO JOB MESSAGE
# ============================================================

def send_no_jobs():

    today = datetime.now(
        timezone.utc
    ).strftime(
        "%d %B %Y"
    )

    message = f"""
<b>🔎 DAILY REMOTE JOB ALERT</b>

📅 {today}

🇧🇩 <b>Target:</b> Bangladesh

No new high-quality remote jobs were found today.

The search covered:
• LinkedIn
• Facebook
• Bdjobs
• Remote jobs
• Public company career pages

I'll search again tomorrow. 🚀
"""

    telegram_send(
        message
    )


# ============================================================
# CLEAN OLD SEEN JOBS
# ============================================================

def cleanup_seen_jobs(seen):

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            days=SEEN_JOB_RETENTION_DAYS
        )
    )

    cleaned = {}

    for jid, data in seen.items():

        timestamp = data.get(
            "sent_at"
        )

        if not timestamp:

            cleaned[jid] = data
            continue

        try:

            sent_at = datetime.fromisoformat(
                timestamp
            )

            if sent_at >= cutoff:

                cleaned[jid] = data

        except Exception:

            cleaned[jid] = data

    return cleaned


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("🚀 BANGLADESH REMOTE JOB FINDER")
    print("=" * 60)
    print()

    seen = load_seen_jobs()

    print(
        f"Previously seen jobs: "
        f"{len(seen)}"
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    raw_jobs = search_all()

    print()
    print(
        f"Raw results: "
        f"{len(raw_jobs)}"
    )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    jobs = deduplicate_jobs(
        raw_jobs
    )

    print(
        f"After deduplication: "
        f"{len(jobs)}"
    )

    # --------------------------------------------------------
    # FILTER + SCORE
    # --------------------------------------------------------

    qualified = []

    for job in jobs:

        if not is_relevant_job(
            job
        ):
            continue

        result = score_job(
            job
        )

        if not result["eligible"]:
            continue

        # Minimum quality threshold
        if result["score"] < 50:
            continue

        if job["id"] in seen:
            continue

        job.update(
            result
        )

        job["company"] = extract_company(
            job
        )

        qualified.append(
            job
        )

    print(
        f"Qualified new jobs: "
        f"{len(qualified)}"
    )

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    qualified.sort(
        key=lambda job: (
            job["score"],
            job["source"] == "LinkedIn",
            job["source"] == "Facebook",
        ),
        reverse=True
    )

    selected = qualified[
        :MAX_JOBS_TO_SEND
    ]

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    if not selected:

        send_no_jobs()

    else:

        send_header(
            selected
        )

        for rank, job in enumerate(
            selected,
            start=1
        ):

            message = format_job_message(
                job,
                rank
            )

            telegram_send(
                message
            )

            # Save as seen
            seen[job["id"]] = {
                "title": job["title"],
                "url": job["url"],
                "source": job["source"],
                "score": job["score"],
                "sent_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            # Telegram rate-limit protection
            time.sleep(
                0.5
            )

    # --------------------------------------------------------
    # CLEAN SEEN DATABASE
    # --------------------------------------------------------

    seen = cleanup_seen_jobs(
        seen
    )

    save_seen_jobs(
        seen
    )

    print()
    print("=" * 60)
    print("✅ JOB SEARCH COMPLETE")
    print("=" * 60)
    print(
        f"Sent: {len(selected)}"
    )
    print(
        f"Seen database: {len(seen)}"
    )
    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nStopped by user."
        )

    except Exception as error:

        print(
            "\n❌ Fatal error:"
        )

        print(
            repr(error)
        )

        raise