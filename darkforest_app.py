import streamlit as st
import subprocess
import shutil
import re

# =========================
# Stockfish Setup
# =========================

def ensure_stockfish():
    engine_path = shutil.which("stockfish")
    if engine_path is None:
        raise RuntimeError(
            "Stockfish not found. Make sure 'stockfish' is listed in packages.txt"
        )
    return engine_path


def run_stockfish(fen, depth=15):
    engine_path = ensure_stockfish()

    process = subprocess.Popen(
        [engine_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    commands = [
        "uci",
        "isready",
        f"position fen {fen}",
        f"go depth {depth}",
        "quit"
    ]

    for cmd in commands:
        process.stdin.write(cmd + "\n")
        process.stdin.flush()

    output = []
    for line in process.stdout:
        line = line.strip()
        output.append(line)
        if line.startswith("bestmove"):
            break

    process.wait()
    return output


# =========================
# UCI Parsing
# =========================

def parse_uci_output(lines):
    info_lines = [l for l in lines if l.startswith("info")]
    bestmove_line = next((l for l in lines if l.startswith("bestmove")), "")

    evaluation = None
    pv = None

    for line in reversed(info_lines):
        if "score cp" in line:
            match = re.search(r"score cp (-?\d+)", line)
            if match:
                evaluation = int(match.group(1)) / 100.0
        elif "score mate" in line:
            match = re.search(r"score mate (-?\d+)", line)
            if match:
                evaluation = f"Mate in {match.group(1)}"

        if " pv " in line and pv is None:
            pv = line.split(" pv ", 1)[1]

        if evaluation is not None and pv is not None:
            break

    bestmove = bestmove_line.split(" ")[1] if bestmove_line else None

    return {
        "evaluation": evaluation,
        "bestmove": bestmove,
        "pv": pv
    }


# =========================
# Streamlit UI
# =========================

st.set_page_config(
    page_title="Dark Forest Compass",
    layout="centered"
)

st.title("♟️ Dark Forest Compass")
st.caption("Stockfish-powered positional analysis")

fen = st.text_area(
    "Enter FEN position",
    value="r1bqkbnr/pppppppp/n7/8/8/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 1",
    height=100
)

depth = st.slider(
    "Analysis Depth",
    min_value=5,
    max_value=25,
    value=15
)

analyze = st.button("Analyze Position")

if analyze:
    if not fen.strip():
        st.error("Please enter a FEN string.")
    else:
        with st.spinner("Analyzing with Stockfish..."):
            try:
                raw_output = run_stockfish(fen, depth)
                parsed = parse_uci_output(raw_output)

                st.subheader("🔍 Analysis Results")

                st.markdown(f"**Best Move:** `{parsed['bestmove']}`")

                if isinstance(parsed["evaluation"], str):
                    st.markdown(f"**Evaluation:** {parsed['evaluation']}")
                elif parsed["evaluation"] is not None:
                    st.markdown(f"**Evaluation:** {parsed['evaluation']:+.2f}")
                else:
                    st.markdown("**Evaluation:** unavailable")

                if parsed["pv"]:
                    st.markdown("**Principal Variation:**")
                    st.code(parsed["pv"])

                with st.expander("Raw Stockfish Output"):
                    st.code("\n".join(raw_output))

            except Exception as e:
                st.error("Stockfish analysis failed.")
                st.exception(e)

st.markdown("---")
st.caption("Runs entirely in the browser using Streamlit + Stockfish")    proc = subprocess.Popen(
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
