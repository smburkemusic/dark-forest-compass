import streamlit as st
import subprocess
import shutil
import re

# =========================
# Stockfish Setup
# =========================

def ensure_stockfish():
    """
    Locate Stockfish installed by packages.txt
    """
    engine_path = shutil.which("stockfish")
    if engine_path is None:
        raise RuntimeError(
            "Stockfish not found. Make sure 'stockfish' is listed in packages.txt"
        )
    return engine_path


def run_stockfish(fen, depth=15):
    """
    Run Stockfish and return raw UCI output lines
    """
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
    """
    Extract evaluation, best move, and PV
    """
    info_lines = [l for l in lines if l.startswith("info")]
    bestmove_line = next((l for l in lines if l.startswith("bestmove")), "")

    evaluation = None
    pv = None

    for line in reversed(info_lines):
        if "score cp" in line and evaluation is None:
            match = re.search(r"score cp (-?\d+)", line)
            if match:
                evaluation = int(match.group(1)) / 100.0

        if "score mate" in line and evaluation is None:
            match = re.search(r"score mate (-?\d+)", line)
            if match:
                evaluation = f"Mate in {match.group(1)}"

        if " pv " in line and pv is None:
            pv = line.split(" pv ", 1)[1]

        if evaluation is not None and pv is not None:
            break

    bestmove = None
    if bestmove_line:
        parts = bestmove_line.split()
        if len(parts) >= 2:
            bestmove = parts[1]

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
st.caption("A glow-in-the-dark compass for the Dark Forest")

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
        st.error("Please enter a valid FEN string.")
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
st.caption("Runs entirely in the browser using Streamlit + Stockfish")
