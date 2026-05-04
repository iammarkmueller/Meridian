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
RESEND_KEY   = os.environ.get("RESEND_API_KEY", "")
PORT         = int(os.environ.get("PORT", 10000))
DIR          = os.path.dirname(os.path.abspath(__file__))


def supabase(method, path, body=None, token=None):
    url = SUPABASE_URL.rstrip("/") + "/rest/v1" + path
    headers = {
        "Content-Type":       "application/json",
        "apikey":             SUPABASE_KEY,
        "Authorization":      "Bearer " + SUPABASE_KEY,  # Always use service key to bypass RLS
        "Prefer":             "return=representation",
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



# ── RESEND EMAIL ─────────────────────────────────────────────────────────────

def send_invite_email(to_email, to_name, company_name, manager_name,
                      manager_email, role, temp_password, app_url):
    """Send a branded Meridian invite email via Resend."""
    if not RESEND_KEY:
        print("[email] RESEND_API_KEY not set — skipping invite email")
        return False

    role_label = {"admin": "Admin", "manager": "Manager"}.get(role, "Field Worker")
    first_name = to_name.split()[0] if to_name else "there"

    html = (
        "<!DOCTYPE html>"
        "<html lang='en'><head><meta charset='UTF-8'>"
        "<title>You have been invited to Meridian</title></head>"
        "<body style='margin:0;padding:0;background:#f4f1eb;font-family:Georgia,serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f4f1eb;padding:32px 16px'>"
        "<tr><td align='center'>"
        "<table width='580' cellpadding='0' cellspacing='0' style='max-width:580px;width:100%'>"

        # HEADER
        "<tr><td style='background:#05172f;border-radius:12px 12px 0 0;padding:32px 40px 28px;text-align:center'>"
        "<p style='margin:0 0 18px;font-family:Georgia,serif;font-size:20px;font-weight:700;color:#e8dfc8;letter-spacing:.14em'>&#9830; MERIDIAN</p>"
        "<div style='width:40px;height:1.5px;background:#C2A072;opacity:.6;margin:0 auto 18px'></div>"
        f"<p style='margin:0;font-family:Georgia,serif;font-size:22px;font-weight:700;color:#e8dfc8;line-height:1.35'>You're invited to join<br>{company_name}</p>"
        "<p style='margin:8px 0 0;font-family:Arial,sans-serif;font-size:13px;color:#C2A072;letter-spacing:.04em'>Field Intelligence Platform</p>"
        "</td></tr>"

        # BODY
        "<tr><td style='background:#ffffff;padding:36px 40px;font-family:Arial,sans-serif'>"
        f"<p style='margin:0 0 12px;font-size:15px;color:#1a1410;font-weight:bold'>Hi {first_name},</p>"
        f"<p style='margin:0 0 20px;font-size:14px;color:#3a3028;line-height:1.75'>"
        f"<strong>{manager_name}</strong> has added you to <strong>{company_name}</strong> on Meridian &mdash; "
        "your team's AI-powered field intelligence platform. You'll be able to photograph job site issues, "
        "get instant SOP-matched repair checklists, and log field reports directly from your phone.</p>"

        # CREDENTIALS CARD
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f7f4ef;border-left:3px solid #C2A072;border-radius:0 8px 8px 0;margin-bottom:24px'>"
        "<tr><td style='padding:16px 20px'>"
        "<table width='100%' cellpadding='0' cellspacing='0'>"
        f"<tr><td style='font-size:12px;color:#7a6e62;width:96px;padding:5px 0'>Your email</td><td style='font-size:13px;color:#1a1410;font-weight:bold;padding:5px 0'>{to_email}</td></tr>"
        f"<tr><td style='font-size:12px;color:#7a6e62;padding:5px 0'>Temp password</td><td style='font-size:14px;color:#1a1410;font-weight:bold;padding:5px 0;font-family:Courier New,monospace;letter-spacing:.06em'>{temp_password}</td></tr>"
        f"<tr><td style='font-size:12px;color:#7a6e62;padding:5px 0'>Your role</td><td style='font-size:13px;color:#1a1410;font-weight:bold;padding:5px 0'>{role_label}</td></tr>"
        f"<tr><td style='font-size:12px;color:#7a6e62;padding:5px 0'>Company</td><td style='font-size:13px;color:#1a1410;font-weight:bold;padding:5px 0'>{company_name}</td></tr>"
        "</table></td></tr></table>"

        # CTA BUTTON
        "<table width='100%' cellpadding='0' cellspacing='0' style='margin-bottom:28px'>"
        "<tr><td align='center'>"
        f"<a href='{app_url}' style='display:inline-block;background:#C2A072;color:#05172f;font-family:Georgia,serif;font-size:15px;font-weight:700;padding:14px 40px;border-radius:8px;text-decoration:none;letter-spacing:.04em'>Open Meridian &rarr;</a>"
        "</td></tr></table>"

        # STEPS
        "<p style='margin:0 0 12px;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#9a8a78'>Getting started</p>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='margin-bottom:24px'><tr><td>"
        "<table cellpadding='0' cellspacing='0' style='margin-bottom:12px;width:100%'><tr>"
        "<td style='width:26px;height:24px;background:#05172f;border-radius:50%;text-align:center;vertical-align:middle;font-size:11px;font-weight:700;color:#C2A072;font-family:Georgia,serif'>1</td>"
        "<td style='padding-left:12px;font-size:13px;color:#3a3028;line-height:1.6'><strong style='color:#1a1410'>Sign in</strong> using your email and the temporary password above.</td>"
        "</tr></table>"
        "<table cellpadding='0' cellspacing='0' style='margin-bottom:12px;width:100%'><tr>"
        "<td style='width:26px;height:24px;background:#05172f;border-radius:50%;text-align:center;vertical-align:middle;font-size:11px;font-weight:700;color:#C2A072;font-family:Georgia,serif'>2</td>"
        "<td style='padding-left:12px;font-size:13px;color:#3a3028;line-height:1.6'><strong style='color:#1a1410'>Change your password</strong> immediately after signing in.</td>"
        "</tr></table>"
        "<table cellpadding='0' cellspacing='0' style='width:100%'><tr>"
        "<td style='width:26px;height:24px;background:#05172f;border-radius:50%;text-align:center;vertical-align:middle;font-size:11px;font-weight:700;color:#C2A072;font-family:Georgia,serif'>3</td>"
        "<td style='padding-left:12px;font-size:13px;color:#3a3028;line-height:1.6'><strong style='color:#1a1410'>Run your first analysis</strong> &mdash; photograph a site issue and get an instant SOP-matched checklist.</td>"
        "</tr></table>"
        "</td></tr></table>"

        # SECURITY NOTICE
        "<table width='100%' cellpadding='0' cellspacing='0' style='margin-bottom:24px'>"
        f"<tr><td style='background:#f0ece3;border-radius:8px;padding:14px 18px;font-size:12px;color:#7a6e62;line-height:1.6'>"
        f"<strong style='color:#5a4e42'>Security note:</strong> Meridian will never ask for your password over email or phone. "
        f"If you did not expect this invitation, contact {manager_name} at "
        f"<a href='mailto:{manager_email}' style='color:#8B6834'>{manager_email}</a> before signing in."
        "</td></tr></table>"

        f"<p style='margin:0;font-size:12px;color:#9a8a78;line-height:1.7'>Questions? Contact your manager at "
        f"<a href='mailto:{manager_email}' style='color:#8B6834'>{manager_email}</a>.</p>"
        "</td></tr>"

        # FOOTER
        "<tr><td style='background:#05172f;border-radius:0 0 12px 12px;padding:22px 40px;text-align:center'>"
        "<p style='margin:0 0 6px;font-family:Georgia,serif;font-size:13px;color:#C2A072;letter-spacing:.1em'>MERIDIAN</p>"
        f"<p style='margin:0;font-size:11px;color:rgba(194,160,114,.45);line-height:1.7'>"
        f"AI Field Intelligence for the Trades &nbsp;&#9830;&nbsp; meridianfi.app<br>"
        f"You received this because {manager_name} invited you to join their team.<br>"
        "&copy; 2026 Meridian. All rights reserved.</p>"
        "</td></tr>"

        "</table></td></tr></table>"
        "</body></html>"
    )

    payload = json.dumps({
        "from":    "Meridian <team@meridianfi.app>",
        "to":      [to_email],
        "subject": f"You have been invited to join Meridian \u2014 {company_name}",
        "html":    html,
    }).encode()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": "Bearer " + RESEND_KEY,
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            print(f"[email] Invite sent to {to_email} — id: {result.get('id')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[email] Resend error {e.code}: {e.read().decode()}")
        return False
    except Exception as ex:
        print(f"[email] Unexpected error: {ex}")
        return False

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
            "/api/analyses/detail":    self.handle_analysis_detail,
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
        print("  Save analysis status:" + str(status) + " data:" + str(data)[:200])
        if status not in (200, 201):
            self.send_json(500, {"error": "Failed to save: " + str(data)}); return
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
        status_a, analyses = supabase("GET",
            "/analyses?company_id=eq." + cid +
            "&order=created_at.desc&limit=50")
        print("  Dashboard analyses status:" + str(status_a) + " count:" + str(len(analyses) if isinstance(analyses,list) else analyses))
        analyses = analyses if isinstance(analyses, list) else []
        # Enrich with worker names
        for a in analyses:
            if a.get("worker_id"):
                _, urows = supabase("GET", "/users?id=eq." + a["worker_id"] + "&select=full_name")
                if isinstance(urows,list) and urows:
                    a["worker_name"] = urows[0].get("full_name","Unknown")
                else:
                    a["worker_name"] = "Unknown"
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
        print(f"[invite] Request received — email: {body.get('email')} role: {body.get('role')}")
        if not token:
            print("[invite] No token — rejecting")
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile or profile.get("role") not in ("manager","admin"):
            print(f"[invite] Auth failed — profile: {profile}")
            self.send_json(403, {"error": "Managers only"}); return
        print(f"[invite] Auth OK — manager: {profile.get('full_name')} company: {profile.get('company_id')}")
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
            print(f"[invite] Supabase account created — id: {new_user.get('id')}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            print(f"[invite] Supabase error {e.code}: {err_body}")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {}
            if err_json.get("error_code") == "email_exists" or e.code == 422:
                self.send_json(409, {"error": "A user with this email address is already registered. Check the Team list or delete the existing account in Supabase first."})
            else:
                self.send_json(400, {"error": "Could not create account. Check Render logs for details."})
            return
        except Exception as ex:
            print(f"[invite] Unexpected error creating account: {ex}")
            self.send_json(500, {"error": str(ex)}); return
        supabase("POST", "/users", {
            "id":         new_user["id"],
            "company_id": profile["company_id"],
            "full_name":  body.get("full_name", ""),
            "role":       body.get("role", "worker"),
        })

        # Fetch company name for the email
        _, companies = supabase("GET", "/companies?id=eq." + profile["company_id"] + "&select=name")
        company_name = companies[0]["name"] if isinstance(companies, list) and companies else "your company"

        # Derive app URL from the request Host header
        host = self.headers.get("Host", "localhost")
        scheme = "https" if "localhost" not in host else "http"
        app_url = f"{scheme}://{host}"

        email_sent = send_invite_email(
            to_email      = body.get("email"),
            to_name       = body.get("full_name", ""),
            company_name  = company_name,
            manager_name  = profile.get("full_name", "Your manager"),
            manager_email = auth_user.get("email", ""),
            role          = body.get("role", "worker"),
            temp_password = body.get("password", "ChangeMe123!"),
            app_url       = app_url,
        )

        print(f"[invite] Complete — user_id: {new_user['id']} email_sent: {email_sent}")
        self.send_json(200, {"ok": True, "user_id": new_user["id"], "email_sent": email_sent})

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
        if status_filter == "closed":
            filter_str = "&completed=eq.true"
        else:
            filter_str = "&completed=eq.false"
        _, analyses = supabase("GET",
            "/analyses?worker_id=eq." + auth_user["id"] +
            filter_str + "&order=created_at.desc&limit=50")
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
        reopen      = body.get("reopen", False)
        completed   = not reopen
        # Mark all checklist items
        supabase("PATCH",
            "/checklist_items?analysis_id=eq." + analysis_id,
            {"completed": completed})
        # Mark the analysis itself
        supabase("PATCH",
            "/analyses?id=eq." + analysis_id,
            {"completed": completed})
        self.send_json(200, {"ok": True, "completed": completed})

    def handle_analysis_detail(self):
        token = self.get_token()
        body  = self.read_body()
        if not token:
            self.send_json(401, {"error": "Not authenticated"}); return
        auth_user, profile = get_user_from_token(token)
        if not profile:
            self.send_json(401, {"error": "User not found"}); return
        analysis_id = body.get("analysis_id", "")
        if not analysis_id:
            self.send_json(400, {"error": "analysis_id required"}); return
        # Fetch the analysis (scoped to company)
        status_a, rows = supabase("GET",
            "/analyses?id=eq." + analysis_id +
            "&company_id=eq." + profile["company_id"])
        if status_a != 200 or not rows:
            self.send_json(404, {"error": "Analysis not found"}); return
        analysis = rows[0]
        # Enrich with worker name
        if analysis.get("worker_id"):
            _, urows = supabase("GET", "/users?id=eq." + analysis["worker_id"] + "&select=full_name")
            if isinstance(urows, list) and urows:
                analysis["worker_name"] = urows[0].get("full_name", "Unknown")
        # Fetch checklist items ordered by step
        _, items = supabase("GET",
            "/checklist_items?analysis_id=eq." + analysis_id + "&order=step.asc")
        self.send_json(200, {
            "analysis": analysis,
            "checklist": items if isinstance(items, list) else []
        })

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
