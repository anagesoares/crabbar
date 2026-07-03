#!/usr/bin/env python3
# <xbar.title>Clawdmeter (barra de menus)</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.author>Autora: Ana G. Soares (adaptado do Clawdmeter)</xbar.author>
# <xbar.desc>Uso do Claude Code na barra de menus: gasto (tokens/$) de arquivos locais via ccusage, mais o % do limite de 5h/7d via um ping mínimo na API.</xbar.desc>
# <xbar.dependencies>python3,node(npx),ccusage</xbar.dependencies>
#
# Plugin SwiftBar/xbar. Intervalo no nome do arquivo (.2m.) = re-executa a cada 2 minutos.
# Só stdlib, sem venv. Ver o README do repositório.
#
# Duas fontes de dados:
#   1. Gasto (tokens + $), custo ZERO: `ccusage -j` lê ~/.claude/projects/**/*.jsonl localmente.
#   2. Limite % (5h/7d), custo mínimo: POST de 1 token na API da Anthropic, lido dos headers da resposta.
#      Defina CLAWD_NO_PING=1 pra desligar o ping de vez (aí fica 100% grátis, sem o % do limite).

import getpass
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEYCHAIN_SERVICE = "Claude Code-credentials"
API_URL = "https://api.anthropic.com/v1/messages"
API_HEADERS = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.5",
}
API_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}

# Color thresholds for the rate-limit %. Pares "claro,escuro": 1º p/ tema claro
# (fundo branco do dropdown → tons escuros), 2º p/ tema escuro (tons mais vivos).
GREEN = "#6f42c1,#c9a8ff"  # roxo (nível "ok", baixo uso)
AMBER = "#9a6700,#e3b341"  # âmbar (70–89%)
RED = "#cf222e,#ff7b72"    # vermelho (≥90%)
DIM = "#57606a,#9aa4af"    # cinza de apoio (cabeçalhos, status)


def color_for(pct):
    if pct is None:
        return DIM
    if pct >= 90:
        return RED
    if pct >= 70:
        return AMBER
    return GREEN


# ---------------------------------------------------------------- spend (free)
def run_ccusage():
    """Return ccusage JSON dict, or None. Tries global `ccusage` then `npx`."""
    candidates = [
        ["ccusage", "-j"],
        ["npx", "--yes", "ccusage@latest", "-j"],
    ]
    override = os.environ.get("CLAWD_CCUSAGE_CMD")
    if override:
        candidates.insert(0, override.split())
    env = dict(os.environ)
    # npx/node need a sane PATH when launched from SwiftBar's minimal env.
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    for cmd in candidates:
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, env=env
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if out.returncode != 0 or not out.stdout.strip():
            continue
        try:
            return json.loads(out.stdout)
        except json.JSONDecodeError:
            continue
    return None


def parse_spend(data):
    """Extract today's and all-time spend from ccusage JSON."""
    if not data:
        return None
    today = time.strftime("%Y-%m-%d")
    daily = data.get("daily") or []
    day = next((d for d in daily if d.get("period") == today), None)
    if day is None and daily:
        day = daily[-1]  # fall back to most recent day present
    totals = data.get("totals") or {}
    day = day or {}

    def io(d):  # "novo": trabalho real = input + output
        return d.get("inputTokens", 0) + d.get("outputTokens", 0)

    def cache(d):  # cache write + read (releitura de contexto, infla o total)
        return d.get("cacheCreationTokens", 0) + d.get("cacheReadTokens", 0)

    return {
        "today_tok": day.get("totalTokens", 0),
        "today_cost": day.get("totalCost", 0.0),
        "today_io": io(day),
        "today_cache": cache(day),
        "today_is_today": bool(day and day.get("period") == today),
        "all_tok": totals.get("totalTokens", 0),
        "all_cost": totals.get("totalCost", 0.0),
        "all_io": io(totals),
        "all_cache": cache(totals),
    }


# ------------------------------------------------------------ limit (tiny cost)
def extract_token(blob):
    blob = (blob or "").strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None


def read_token():
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", getpass.getuser(), "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return extract_token(out.stdout)


def poll_limit():
    """Return {s, sr, w, wr, st} from rate-limit headers, or None."""
    if os.environ.get("CLAWD_NO_PING") == "1":
        return None
    token = read_token()
    if not token:
        return None
    headers = dict(API_HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        API_URL, data=json.dumps(API_BODY).encode(), headers=headers, method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        h = resp.headers
    except urllib.error.HTTPError as e:
        h = e.headers  # rate-limit headers are present even on 429/4xx
    except (urllib.error.URLError, OSError):
        return None
    if h is None:
        return None

    now = time.time()

    def pct(name):
        try:
            return int(round(float(h.get(name, "")) * 100))
        except (TypeError, ValueError):
            return None

    def mins(name):
        try:
            m = (float(h.get(name, "")) - now) / 60.0
        except (TypeError, ValueError):
            return None
        return int(round(m)) if m > 0 else 0

    s = pct("anthropic-ratelimit-unified-5h-utilization")
    w = pct("anthropic-ratelimit-unified-7d-utilization")
    if s is None and w is None:
        return None
    return {
        "s": s, "sr": mins("anthropic-ratelimit-unified-5h-reset"),
        "w": w, "wr": mins("anthropic-ratelimit-unified-7d-reset"),
        "st": h.get("anthropic-ratelimit-unified-5h-status", "unknown"),
    }


# ----------------------------------------------------------------- formatting
def fmt_tokens(n):
    n = n or 0
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def fmt_mins(m):
    if m is None:
        return "?"
    if m >= 1440:  # >= 24h → dias + horas
        return f"{m // 1440}d {(m % 1440) // 60}h"
    if m >= 60:
        return f"{m // 60}h {m % 60}m"
    return f"{m}m"


# Texto principal forte (legível nos dois temas) e cabeçalho de seção.
TEXT = "#1f2328,#e6edf3"          # quase-preto no claro / quase-branco no escuro
FONT = f"size=14 font=Menlo color={TEXT}"   # linhas de dado
HEAD = f"size=12 color={DIM}"               # cabeçalhos de seção


def main():
    spend = parse_spend(run_ccusage())
    limit = poll_limit()

    # ----- menu bar title -----
    TITLE = "#ffffff"  # branco puro (sem par claro/escuro)
    if limit and (limit["s"] is not None or limit["w"] is not None):
        s, w = limit["s"], limit["w"]
        st = f"{s if s is not None else '?'}%·{w if w is not None else '?'}%"
        print(f"🦀 {st} | color={TITLE}")
    elif spend:
        print(f"🦀 ${spend['all_cost']:.2f} | color={TITLE}")
    else:
        print(f"🦀 – | color={TITLE}")

    print("---")

    # ----- limit section -----
    if limit and (limit["s"] is not None or limit["w"] is not None):
        s, w = limit["s"], limit["w"]
        print(f"Rate limit | {HEAD}")
        if s is not None:
            print(f"Sessão (5h):  {s}%   reset em {fmt_mins(limit['sr'])} | "
                  f"size=14 font=Menlo color={color_for(s)}")
        if w is not None:
            print(f"Semanal (7d): {w}%   reset em {fmt_mins(limit['wr'])} | "
                  f"size=14 font=Menlo color={color_for(w)}")
        st = limit.get("st", "unknown")
        st_color = RED if st == "limited" else TEXT
        print(f"Status: {st} | size=12 color={st_color}")
    elif os.environ.get("CLAWD_NO_PING") == "1":
        print(f"Limite: ping desligado (CLAWD_NO_PING=1) | {HEAD}")
    else:
        print(f"Limite indisponível (sem token ou offline) | {HEAD}")

    print("---")

    # ----- spend section (free, from ccusage) -----
    if spend:
        label = "Hoje" if spend["today_is_today"] else "Último dia"
        print(f"Gasto (local, custo zero) | {HEAD}")
        print(f"{label}:  {fmt_tokens(spend['today_tok'])} tok   "
              f"${spend['today_cost']:.2f} | {FONT}")
        print(f"  ↳ novo (in+out): {fmt_tokens(spend['today_io'])}   "
              f"cache: {fmt_tokens(spend['today_cache'])} | {HEAD} font=Menlo")
        print(f"Total: {fmt_tokens(spend['all_tok'])} tok   "
              f"${spend['all_cost']:.2f} | {FONT}")
        print(f"  ↳ novo (in+out): {fmt_tokens(spend['all_io'])}   "
              f"cache: {fmt_tokens(spend['all_cache'])} | {HEAD} font=Menlo")
    else:
        print(f"Gasto indisponível (ccusage falhou) | {HEAD}")
        print(f"Instalar: npm i -g ccusage | {HEAD}")

    print("---")
    print(f"Atualizado {time.strftime('%H:%M:%S')} | {HEAD}")
    print("Atualizar agora | refresh=true")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the menu bar
        print("🦀 ⚠️")
        print("---")
        print(f"Erro: {e} | color={RED} size=11")
        print("Atualizar agora | refresh=true")
        sys.exit(0)
