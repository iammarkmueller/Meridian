#!/usr/bin/env python3
"""
Meridian - Web Server
Serves the app, proxies Anthropic API calls, and integrates with Supabase.
Required environment variables:
  ANTHROPIC_API_KEY    - Anthropic API key
  SUPABASE_URL         - Supabase project URL
  SUPABASE_SERVICE_KEY - Supabase service role key
"""

import http.server
import urllib.request
import urllib.error
import json
import os
import sys
import socketserver

API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PORT         = int(os.environ.get("PORT", 8765))
DIR          = os.path.dirname(os.path.abspath(__file__))


def supabase(method, path, body=None, token=None):
    url = SUPABASE_URL.rstrip("/") + "/rest/v1" + path
    headers = {
        "Content-Type":  "application/json",
        "apikey":        SUPABASE_KEY,
        "Authorization": "Bearer " + (token or SUPABASE_KEY),
        "Prefer":        "return=representation",
    }
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 500, {"error": str(ex)}


def supabase_auth(path, body):
    url = SUPABASE_URL.rstrip("/") + "/auth/v1" + path
    headers = {
        "Content-Type": "application/json",
        "apikey":       SUPABASE_KEY,
    }
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as ex:
        return 500, {"error": str(ex)}


def get_user_from_token(token):
    url = SUPABASE_URL.rstrip("/") + "/auth/v1/user"
    headers = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + token}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            auth_user = json.loads(r.read())
        # Use service key (not user token) to bypass RLS for profile lookup
        status, rows = supabase("GET",
            "/users?id=eq." + auth_user["id"] + "&select=*,companies(name,plan)")
        print("  get_user_from_token: status=" + str(status) + " rows=" + str(len(rows) if isinstance(rows,list) else rows))
        profile = rows[0] if status == 200 and isinstance(rows,list) and rows else None
        return auth_user, profile
    except Exception as ex:
        print("  get_user_from_token error:", ex)
        return None, None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, fmt, *args):
        print("  " + self.command + " " + self.path)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/sopsearch-vision.html"
        elif self.path in ("/dashboard", "/dashboard/"):
            self.path = "/dashboard.html"
        super().do_GET()

    def do_POST(self):
        routes = {
            "/api/login":              self.handle_login,
            "/api/analyze":            self.handle_analyze,
            "/api/sops":               self.handle_get_sops,
            "/api/sops/add":           self.handle_add_sop,
            "/api/sops/delete":        self.handle_delete_sop,
            "/api/analyses/save":      self.handle_save_analysis,
            "/api/analyses/mine":      self.handle_my_analyses,
            "/api/analyses/complete":  self.handle_complete_analysis,
            "/api/checklist/update":   self.handle_update_checklist,
            "/api/dashboard":          self.handle_dashboard,
            "/api/alerts/dismiss":     self.handle_dismiss_alert,
            "/api/team/invite":        self.handle_invite,
            "/api/team/list":          self.handle_team_list,
        }
        h = routes.get(self.path)
        if h:
            h()
        else:
            self.send_error(404)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def get_token(self):
        auth = self.headers.get("Authorization", "")
        return auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else None

    def handle_login(self):
        body = self.read_body()
        status, data = supabase_auth("/token?grant_type=password", {
            "email": body.get("email", ""),
            "password": body.get("password", "")
        })
        if status != 200:
            self.send_json(401, {"error": "Invalid email or password"})
            return
        token   = data.get("access_token")
        user_id = data.get("user", {}).get("id", "")
        s2, rows = supabase("GET",
            "/users?id=eq." + user_id + "&select=*,companies(name,plan)")
        profile = rows[0] if s2 == 200 and rows else {}
        self.send_json(200, {
            "token":      token,
            "user_id":    user_id,
            "email":      body.get("email", ""),
            "full_name":  profile.get("full_name", ""),
            "role":       profile.get("role", "worker"),
            "company_id": profile.get("company_id", ""),
            "company":    profile.get("companies", {})
        })

    def handle_get_sops(self):
        token = self.get_token()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        company_id = profile["company_id"]
        # Use service key to bypass RLS and reliably fetch all company SOPs
        status, sops = supabase("GET",
            "/sops?company_id=eq." + company_id + "&order=created_at.asc")
        print("  GET SOPs for company " + company_id + " -> status " + str(status) + " count " + str(len(sops) if isinstance(sops,list) else 0))
        self.send_json(200, {"sops": sops if status == 200 else []})

    def handle_add_sop(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile or profile.get("role") not in ("manager", "admin"):
            self.send_json(403, {"error": "Managers only"}); return
        sop = {
            "company_id": profile["company_id"],
            "name":       body.get("name", ""),
            "sop_id":     body.get("sop_id", ""),
            "category":   body.get("category", "ops"),
            "content":    body.get("content", ""),
            "version":    body.get("version", "1.0"),
            "source":     body.get("source", ""),
            "created_by": auth_user["id"],
        }
        status, data = supabase("POST", "/sops", sop)
        print("  ADD SOP status:" + str(status) + " data:" + str(data)[:200])
        self.send_json(200 if status in (200, 201) else 500,
            {"sop": data[0] if isinstance(data, list) else data})

    def handle_delete_sop(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile or profile.get("role") not in ("manager", "admin"):
            self.send_json(403, {"error": "Managers only"}); return
        supabase("DELETE",
            "/sops?id=eq." + body.get("id","") + "&company_id=eq." + profile["company_id"])
        self.send_json(200, {"ok": True})

    def handle_analyze(self):
        if not API_KEY:
            self.send_json(500, {"error": {"message": "ANTHROPIC_API_KEY not set"}}); return
        body = self.read_body()
        if "model" not in body:
            body["model"] = "claude-sonnet-4-5"
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type":      "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key":         API_KEY,
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_body = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)

    def handle_save_analysis(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        analysis = {
            "company_id":   profile["company_id"],
            "worker_id":    auth_user["id"],
            "issue_title":  body.get("issue_title", ""),
            "issue_desc":   body.get("issue_description", ""),
            "severity":     body.get("severity", "MEDIUM"),
            "tags":         body.get("tags", []),
            "summary":      body.get("summary", ""),
            "matched_sops": json.dumps(body.get("matched_sops", [])),
            "raw_result":   json.dumps(body),
        }
        status, data = supabase("POST", "/analyses", analysis)
        if status not in (200, 201):
            self.send_json(500, {"error": "Failed to save"}); return
        analysis_id = data[0]["id"] if isinstance(data, list) else data.get("id","")
        for item in body.get("checklist", []):
            supabase("POST", "/checklist_items", {
                "analysis_id": analysis_id,
                "step":        item.get("step"),
                "title":       item.get("title", ""),
                "detail":      item.get("detail", ""),
                "ref":         item.get("ref", ""),
                "priority":    item.get("priority", "standard"),
                "completed":   False,
            })
        if body.get("severity") == "HIGH":
            supabase("POST", "/alerts", {
                "company_id":  profile["company_id"],
                "analysis_id": analysis_id,
                "type":        "severity",
                "message":     "HIGH severity: " + body.get("issue_title","") +
                               " — " + profile.get("full_name","a worker"),
            })
        self.send_json(200, {"analysis_id": analysis_id})

    def handle_dashboard(self):
        token = self.get_token()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile or profile.get("role") not in ("manager", "admin"):
            self.send_json(403, {"error": "Managers only"}); return
        cid = profile["company_id"]
        _, analyses = supabase("GET",
            "/analyses?company_id=eq." + cid +
            "&select=*,users(full_name)&order=created_at.desc&limit=50")
        analyses = analyses if isinstance(analyses, list) else []
        _, alerts = supabase("GET",
            "/alerts?company_id=eq." + cid +
            "&dismissed=eq.false&order=sent_at.desc&limit=10")
        _, team = supabase("GET",
            "/users?company_id=eq." + cid + "&select=*")
        self.send_json(200, {
            "analyses": analyses,
            "alerts":   alerts  if isinstance(alerts, list) else [],
            "team":     team    if isinstance(team, list)   else [],
            "counts": {
                "high":   sum(1 for a in analyses if a.get("severity")=="HIGH"),
                "medium": sum(1 for a in analyses if a.get("severity")=="MEDIUM"),
                "low":    sum(1 for a in analyses if a.get("severity")=="LOW"),
                "total":  len(analyses),
            }
        })

    def handle_dismiss_alert(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        supabase("PATCH", "/alerts?id=eq." + body.get("id",""), {"dismissed": True})
        self.send_json(200, {"ok": True})

    def handle_invite(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile or profile.get("role") not in ("manager","admin"):
            self.send_json(403, {"error": "Managers only"}); return
        url = SUPABASE_URL.rstrip("/") + "/auth/v1/admin/users"
        headers = {
            "Content-Type":  "application/json",
            "apikey":        SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY,
        }
        req = urllib.request.Request(url,
            data=json.dumps({
                "email":         body.get("email"),
                "password":      body.get("password", "ChangeMe123!"),
                "email_confirm": True,
            }).encode(),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                new_user = json.loads(r.read())
        except urllib.error.HTTPError as e:
            self.send_json(400, {"error": str(e.read())}); return
        supabase("POST", "/users", {
            "id":         new_user["id"],
            "company_id": profile["company_id"],
            "full_name":  body.get("full_name", ""),
            "role":       body.get("role", "worker"),
        })
        self.send_json(200, {"ok": True, "user_id": new_user["id"]})

    def handle_team_list(self):
        token = self.get_token()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "Not found"}); return
        _, team = supabase("GET",
            "/users?company_id=eq." + profile["company_id"] + "&select=*")
        self.send_json(200, {"team": team if isinstance(team, list) else []})

    def handle_my_analyses(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        status_filter = body.get("status", "open")
        completed_filter = "eq.true" if status_filter == "closed" else "eq.false"
        _, analyses = supabase("GET",
            "/analyses?worker_id=eq." + auth_user["id"] +
            "&order=created_at.desc&limit=50")
        self.send_json(200, {"analyses": analyses if isinstance(analyses, list) else []})

    def handle_complete_analysis(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        analysis_id = body.get("analysis_id", "")
        # Mark all checklist items as complete
        supabase("PATCH",
            "/checklist_items?analysis_id=eq." + analysis_id,
            {"completed": True})
        self.send_json(200, {"ok": True})

    def handle_update_checklist(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        analysis_id = body.get("analysis_id", "")
        step        = body.get("step")
        completed   = body.get("completed", False)
        supabase("PATCH",
            "/checklist_items?analysis_id=eq." + analysis_id + "&step=eq." + str(step),
            {"completed": completed})
        self.send_json(200, {"ok": True})

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    missing = [v for v in ["ANTHROPIC_API_KEY","SUPABASE_URL","SUPABASE_SERVICE_KEY"]
               if not os.environ.get(v)]
    if missing:
        print("Missing env vars: " + ", ".join(missing)); sys.exit(1)

    print("=" * 48)
    print("  Meridian  |  http://localhost:" + str(PORT))
    print("  Ctrl+C to stop")
    print("=" * 48)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
