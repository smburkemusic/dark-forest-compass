st.warning("⚠️ NEW VERSION LOADED — Stockfish auto-analysis enabled")


import re
import os
import stat
import platform
import urllib.request
import subprocess
import statistics
from collections import defaultdict

import streamlit as st
import pandas as pd

# ============================
# Stockfish bootstrap
# ============================

def ensure_stockfish():
    system = platform.system().lower()

    if system == "windows":
        url = "https://stockfishchess.org/files/stockfish-windows-x86-64-avx2.zip"
        exe_name = "stockfish.exe"
    elif system == "linux":
        url = "https://stockfishchess.org/files/stockfish-linux-x86-64-avx2.tar"
        exe_name = "stockfish"
    elif system == "darwin":
        url = "https://stockfishchess.org/files/stockfish-macos-x86-64-avx2.tar"
        exe_name = "stockfish"
    else:
        raise RuntimeError("Unsupported operating system")

    if os.path.exists(exe_name):
        return exe_name

    st.info("⬇️ Downloading Stockfish engine…")

    archive = "stockfish_download"
    urllib.request.urlretrieve(url, archive)

    if url.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if "stockfish" in name.lower() and not name.endswith("/"):
                    z.extract(name, ".")
                    os.rename(name, exe_name)
                    break
    else:
        import tarfile
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                if "stockfish" in member.name.lower() and member.isfile():
                    t.extract(member, ".")
                    os.rename(member.name, exe_name)
                    break

    os.remove(archive)
    os.chmod(exe_name, stat.S_IRWXU)
    return exe_name


def run_stockfish(fen, depth):
    engine_path = ensure_stockfish()

    proc = subprocess.Popen(
        [engine_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    commands = [
        "uci",
        "isready",
        f"position fen {fen}",
        f"go depth {depth}",
        "quit",
    ]

    stdout, _ = proc.communicate("\n".join(commands), timeout=60)
    return stdout


# ============================
# Parsing + Analysis
# ============================

INFO_RE = re.compile(
    r"info\s+depth\s+(\d+).*?score\s+(cp|mate)\s+(-?\d+).*?pv\s+(\S+)"
)


class DangerAnalyzer:
    def __init__(self):
        self.data = defaultdict(list)

    def ingest(self, text):
        for line in text.splitlines():
            m = INFO_RE.search(line)
            if not m:
                continue

            depth = int(m.group(1))
            score_type = m.group(2)
            score = int(m.group(3))
            move = m.group(4)

            if score_type == "mate":
                score = 10000 if score > 0 else -10000

            self.data[move].append((depth, score / 100.0))

    def analyze(self):
        results = {}
        if not self.data:
            return results

        max_depth = max(d for series in self.data.values() for d, _ in series)

        for move, series in self.data.items():
            series.sort()
            evals = [e for _, e in series]
            depths = [d for d, _ in series]

            volatility = statistics.pstdev(evals) if len(evals) > 1 else 0.0
            weighted_drift = 0.0
            late_flip = False

            for i in range(len(evals) - 1):
                delta = abs(evals[i + 1] - evals[i])
                weight = (depths[i + 1] / max_depth) ** 2
                weighted_drift += delta * weight

                if evals[i] * evals[i + 1] < 0 and depths[i + 1] >= 0.7 * max_depth:
                    late_flip = True

            results[move] = {
                "end": evals[-1],
                "volatility": volatility,
                "weighted_drift": weighted_drift,
                "late_flip": late_flip,
            }

        return results

    def danger_score(self, info):
        score = info["weighted_drift"] + 0.5 * info["volatility"]
        if info["late_flip"]:
            score += 1.0
        return score


# ============================
# Human Layer
# ============================

def danger_band(info):
    if info["late_flip"] or info["weighted_drift"] > 1.5:
        return "🔴 DANGEROUS"
    if info["weighted_drift"] > 0.6 or info["volatility"] > 0.5:
        return "🟡 UNCLEAR"
    return "🟢 SAFE"


def cluster_moves(analysis):
    clusters = defaultdict(list)
    for move, info in analysis.items():
        signature = (
            round(info["end"], 1),
            round(info["weighted_drift"], 1),
            info["late_flip"],
        )
        clusters[signature].append(move)
    return clusters


# ============================
# Streamlit UI
# ============================

st.set_page_config(page_title="Dark Forest Compass", layout="wide")

st.title("🧭 Dark Forest Compass")
st.caption("A glow-in-the-dark compass for positions where calculation lies.")

fen = st.text_input("FEN position")
depth = st.slider("Analysis depth", 8, 30, 18)
analyze = st.button("Analyze with Stockfish")

raw_output = ""

if analyze and fen.strip():
    with st.spinner("Stockfish is thinking…"):
        raw_output = run_stockfish(fen, depth)

if raw_output:
    analyzer = DangerAnalyzer()
    analyzer.ingest(raw_output)
    analysis = analyzer.analyze()

    rows = []
    for move, info in analysis.items():
        rows.append({
            "Move": move,
            "Danger": round(analyzer.danger_score(info), 2),
            "End Eval": round(info["end"], 2),
            "Weighted Drift": round(info["weighted_drift"], 2),
            "Volatility": round(info["volatility"], 2),
            "Late Flip": "YES" if info["late_flip"] else "NO",
            "Band": danger_band(info),
        })

    df = pd.DataFrame(rows).sort_values("Danger", ascending=False)

    st.subheader("🚨 Move Danger Ranking")
    st.dataframe(df, use_container_width=True)

    st.subheader("🧬 Move Clusters (Same Fate)")
    clusters = cluster_moves(analysis)
    for sig, moves in clusters.items():
        st.markdown(
            f"**{danger_band({'weighted_drift': sig[1], 'volatility': 0, 'late_flip': sig[2]})}** "
            f"→ `{', '.join(moves)}` (end={sig[0]}, drift={sig[1]})"
        )

    with st.expander("🧠 Raw Stockfish Output"):
        st.text(raw_output)
else:
    st.info("Enter a FEN and click Analyze.")
