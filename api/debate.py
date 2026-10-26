import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

PROMPT_TEMPLATE = """You write scripts for a comedy web app called Multiagent Debate. Write a funny scripted debate about this topic: {topic!r}

Cast (use these ids exactly):
- judge = Judge Gavel-9000, a dry, tired moderator
- prof = Professor Pedantic, over-qualifies everything, invents statistics, loves slides and appendices
- chaos = Captain Chaos, loud contrarian, shouts in CAPS, changes their mind mid-sentence
- snack = Sir Snacksalot, always hungry, relates everything to food
- doom = Dr. Doomscroll, paranoid, sees conspiracies, ominous
- sunny = Sunny Bright, relentless optimist who hugs everything

Rules:
1. Turn the topic into one clear question with exactly two answer options (index 0 and 1).
2. Exactly 4 rounds, in this order: "Opening statements" (judge intro, then one opening from each of the five debaters), "Rebuttals" (8 to 10 lines, including one stage direction object like {{"s":"The audience gasps."}}), "Cross-fire" (6 to 8 quick lines), and "Final votes" (exactly 5 lines, one per debater, each with v set to 0 or 1).
3. Every spoken line is at most 35 words. Stay in character. Be silly and good-natured.
4. Each debater must make at least one real, useful point about the actual topic inside the jokes.
5. The final answer is the judge's ruling: 2 to 3 sentences that genuinely resolve the question with a practical recommendation and match the vote result. The note is one short joke line.
6. No insults about real people or groups, and no hot-button politics. If the topic is hateful or harmful, debate a silly food question instead.

Return only one JSON object in this shape:
{{"question":"...","options":["Option A","Option B"],"rounds":[{{"title":"Opening statements","lines":[{{"a":"judge","t":"..."}}]}},{{"title":"Rebuttals","lines":[{{"a":"prof","t":"..."}},{{"s":"stage direction"}}]}},{{"title":"Cross-fire","lines":[{{"a":"chaos","t":"..."}}]}},{{"title":"Final votes","lines":[{{"a":"prof","t":"...","v":0}}]}}],"final":{{"answer":"...","note":"..."}}}}
"""


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_model_json(gemini_data):
    text = gemini_data["candidates"][0]["content"]["parts"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return json.loads(text)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        json_response(self, 204, {})

    def do_POST(self):
        if not os.environ.get("GEMINI_API_KEY"):
            json_response(self, 500, {"error": "missing_api_key"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_data = json.loads(self.rfile.read(length))
            topic = str(request_data.get("topic", "")).strip()
        except (ValueError, json.JSONDecodeError):
            json_response(self, 400, {"error": "invalid_request"})
            return

        if not topic or len(topic) > 120:
            json_response(self, 400, {"error": "invalid_topic"})
            return

        request_body = json.dumps({
            "contents": [{"parts": [{"text": PROMPT_TEMPLATE.format(topic=topic)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.9,
            },
        }).encode("utf-8")
        url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}".format(
            MODEL, os.environ["GEMINI_API_KEY"]
        )

        try:
            request = Request(url, data=request_body, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=55) as response:
                gemini_data = json.loads(response.read())
            script = parse_model_json(gemini_data)
        except HTTPError as error:
            code = "rate_limited" if error.code == 429 else "gemini_error"
            json_response(self, 429 if error.code == 429 else 502, {"error": code})
            return
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, URLError, TimeoutError):
            json_response(self, 502, {"error": "invalid_json"})
            return

        json_response(self, 200, {"script": script})

    def log_message(self, format, *args):
        return
