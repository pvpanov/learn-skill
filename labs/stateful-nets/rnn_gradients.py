"""How far back can a tanh RNN "hear"? Gradient norm of h_T with respect to h_{T-k}, against k.

Session stateful-nets 2026-11-10 (predict-then-run). The owner predicts the curves first; this script measures them.

Set-up (fixed before the run):
  - hidden state h_t in R^32, one "underlying", daily feature vector x_t in R^4 (i.i.d. N(0,1) stand-ins for
    daily market features);
  - h_t = tanh(W h_{t-1} + U x_t + b), W random Gaussian rescaled to spectral radius rho in {0.9, 1.0, 1.2};
  - T = 100 days, k = 1..60 (a 20-60-day lag);
  - d h_T / d h_{T-k} = J_T J_{T-1} ... J_{T-k+1}, with J_t = diag(1 - h_t^2) W (one step's Jacobian);
  - reported: spectral norm (largest singular value) of that product, median over 8 seeds;
    plus the same for a *linear* RNN (no tanh, J_t = W) as a reference, and the mean tanh slope 1 - h^2.

Run (CPU, 2 threads, a second or two):
  $env:OMP_NUM_THREADS = "2"
  python rnn_gradients.py
Writes out/rnn_gradients.txt, .csv and .png.
Follow-ups (tutor): --rhos 0.9 1.2 2 3 (where tanh does explode), --input-scale 0 or 1.5 (saturation), --tag NAME
(writes rnn_gradients_NAME.*).
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import numpy as np  # noqa: E402

N, D, T, KMAX, SEEDS = 32, 4, 100, 60, 8
RHOS = (0.9, 1.0, 1.2)
INPUT_SCALE = 0.5  # size of U x_t relative to a unit-variance pre-activation; fixed before the run
SHOW_K = (1, 5, 10, 20, 40, 60)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def make_w(rng, rho):
    w = rng.standard_normal((N, N)) / np.sqrt(N)
    return w * (rho / np.max(np.abs(np.linalg.eigvals(w))))


def run(rho, seed, linear=False):
    rng = np.random.default_rng(seed)
    w = make_w(rng, rho)
    u = rng.standard_normal((N, D)) * INPUT_SCALE / np.sqrt(D)
    b = rng.standard_normal(N) * 0.1
    x = rng.standard_normal((T + 1, D))
    h = np.zeros((T + 1, N))
    for t in range(1, T + 1):
        a = w @ h[t - 1] + u @ x[t] + b
        h[t] = a if linear else np.tanh(a)
    norms = np.empty(KMAX)
    prod = np.eye(N)
    for k in range(1, KMAX + 1):  # multiply in the Jacobian of step T-k+1
        t = T - k + 1
        jac = w if linear else (1.0 - h[t] ** 2)[:, None] * w
        prod = prod @ jac
        norms[k - 1] = np.linalg.norm(prod, 2)
    slope = 1.0 if linear else float(np.mean(1.0 - h[T - KMAX + 1:] ** 2))
    return norms, slope, float(np.linalg.norm(w, 2))


def main():
    global RHOS, INPUT_SCALE
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rhos", type=float, nargs="+", default=list(RHOS))
    ap.add_argument("--input-scale", type=float, default=INPUT_SCALE)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    RHOS, INPUT_SCALE = tuple(args.rhos), args.input_scale
    stem = "rnn_gradients" + (f"_{args.tag}" if args.tag else "")
    os.makedirs(OUT, exist_ok=True)
    res, lines = {}, []
    for linear in (False, True):
        for rho in RHOS:
            runs = [run(rho, s, linear) for s in range(SEEDS)]
            res[(linear, rho)] = (np.median([r[0] for r in runs], axis=0),
                                  float(np.mean([r[1] for r in runs])), float(np.mean([r[2] for r in runs])))
    head = "k:      " + "".join(f"{k:>11d}" for k in SHOW_K)
    for linear in (False, True):
        lines.append(("LINEAR reference (no tanh)" if linear else "TANH RNN") +
                      f"  ||d h_T / d h_(T-k)||_2, median of {SEEDS} seeds, N={N}, input scale {INPUT_SCALE}")
        lines.append(head)
        for rho in RHOS:
            norms, slope, wn = res[(linear, rho)]
            lines.append(f"rho={rho:<4}" + "".join(f"{norms[k - 1]:>11.3g}" for k in SHOW_K) +
                         f"   mean tanh slope {slope:.2f}, ||W||_2 {wn:.2f}")
        lines.append("")
    for rho in RHOS:  # per-step decay rate fitted on k = 20..60 (log-linear slope)
        n = res[(False, rho)][0]
        rate = float(np.exp(np.polyfit(np.arange(20, KMAX + 1), np.log(n[19:]), 1)[0]))
        lines.append(f"tanh rho={rho}: per-step factor fitted on k=20..60 = {rate:.3f}")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(OUT, stem + ".txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    with open(os.path.join(OUT, stem + ".csv"), "w", encoding="utf-8") as f:
        f.write("k," + ",".join(f"{'lin' if l else 'tanh'}_rho{r}" for l in (False, True) for r in RHOS) + "\n")
        for k in range(1, KMAX + 1):
            f.write(f"{k}," + ",".join(f"{res[(l, r)][0][k - 1]:.6g}" for l in (False, True) for r in RHOS) + "\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ks = np.arange(1, KMAX + 1)
        colours = ("#0f6e78", "#8a5a00", "#a03030", "#5a3d9a", "#2f7a3e", "#555555")
        for rho, c in zip(RHOS, colours * 3):
            ax.semilogy(ks, res[(False, rho)][0], color=c, lw=2, label=f"tanh, rho={rho}")
            ax.semilogy(ks, res[(True, rho)][0], color=c, lw=1, ls="--", label=f"linear, rho={rho}")
        ax.set_xlabel("k (days back)")
        ax.set_ylabel("||d h_T / d h_(T-k)||_2 (log scale)")
        ax.set_title("How much of day T-k still reaches day T")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8, ncol=2)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, stem + ".png"), dpi=120)
    except ImportError:
        print("(matplotlib not installed: no plot)")


if __name__ == "__main__":
    main()
