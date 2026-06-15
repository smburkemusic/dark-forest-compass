import re
import statistics
from collections import defaultdict

import streamlit as st
import pandas as pd

# -----------------------------
# Parsing
# -----------------------------

INFO_RE = re.compile(
    r"info\s+depth\s+(\d+).*?score\s+(cp|mate)\s+(-?\d+).*?pv\s+(\S+)"
)

# -----------------------------
# Core Analysis Engine
# -----------------------------

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

        max_depth = max(
            depth for series in self.data.values() for depth, _ in series
        )

        for move, series in self.data.items():
            series = sorted(series, key=lambda x: x[0])
            depths = [d for d, _ in series]
            evals = [e for _, e in series]

            drift = abs(evals[-1] - evals[0])
            volatility = statistics.pstdev(evals) if len(evals) > 1 else 0.0

            weighted_drift = 0.0
            late_flip = False

            for i in range(len(evals) - 1):
                d2 = depths[i + 1]
                e1, e2 = evals[i], evals[i + 1]

                delta = abs(e2 - e1)
                weight = (d2 / max_depth) ** 2
                weighted_drift += delta * weight

                if e1 * e2 < 0 and d2 >= 0.7 * max_depth:
                    late_flip = True

            results[move] = {
                "start": evals[0],
                "end": evals[-1],
                "drift": drift,
                "volatility": volatility,
                "weighted_drift": weighted_drift,
                "late_flip": late_flip,
            }

        return results

    def danger_score(self, info):
        score = info["weighted_drift"]
        score += 0.5 * info["volatility"]
        if info["late_flip"]:
            score += 1.0
        return score


# -----------------------------
# Human Layer
# -----------------------------

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


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(
    page_title="Dark Forest Compass",
    layout="wide",
)

st.title("🧭 Dark Forest Compass")
st.caption(
    "A glow-in-the-dark compass for positions where calculation lies."
)

st.markdown(
    """
Paste **raw Stockfish UCI output** below  
(`info depth … score … pv …` lines).
"""
)

input_text = st.text_area(
    "Stockfish Output",
    height=300,
    placeholder="Paste Stockfish analysis here…",
)

if input_text.strip():
    analyzer = DangerAnalyzer()
    analyzer.ingest(input_text)
    analysis = analyzer.analyze()

    if not analysis:
        st.warning("No valid Stockfish info lines detected.")
    else:
        rows = []
        for move, info in analysis.items():
            rows.append({
                "Move": move,
                "Danger Score": round(analyzer.danger_score(info), 2),
                "End Eval": round(info["end"], 2),
                "Weighted Drift": round(info["weighted_drift"], 2),
                "Volatility": round(info["volatility"], 2),
                "Late Flip": "YES" if info["late_flip"] else "NO",
                "Band": danger_band(info),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("Danger Score", ascending=False)

        st.subheader("🚨 Move Danger Ranking")
        st.dataframe(df, use_container_width=True)

        clusters = cluster_moves(analysis)

        st.subheader("🧬 Move Clusters (Same Fate)")
        for sig, moves in clusters.items():
            st.markdown(
                f"**{danger_band({'weighted_drift': sig[1], 'volatility': 0, 'late_flip': sig[2]})}**  "
                f"→ `{', '.join(moves)}`  "
                f"(end={sig[0]}, drift={sig[1]})"
            )

        st.subheader("🧠 How to Use This")
        st.markdown(
            """
- 🔴 **DANGEROUS**: looks playable, collapses late  
- 🟡 **UNCLEAR**: requires precision you may not have  
- 🟢 **SAFE**: stable ground  

This tool does **not** tell you *what to play*.  
It tells you **where not to wander blindly**.
"""
        )
else:
    st.info("Waiting for Stockfish output…")
