"""Counter-free, stream-split xoshiro128** shared bit-for-bit with docs/cricket/rng.js.

Each (seed, sim, stream) gets its own 128-bit state from four splitmix32 outputs keyed by
fmix32(fmix32(seed ^ 0x243F6A88) ^ stream) ^ sim (plan section 9.5). Events draw a fixed
number of uniforms from their stream whether they need them or not, so a sim's random
numbers do not depend on how many sims run, which worker runs them, or what other
factors a sensitivity rerun changes. Arrays hold one state row per simulation.
"""
from __future__ import annotations

import numpy as np

STREAMS = {"ball": 0, "over": 1, "innings": 2, "match": 3, "player": 4}
SLOTS = {"ball": 12, "over": 4, "innings": 4, "match": 64, "player": 4}
_M32 = np.uint64(0xFFFFFFFF)


def _u32(x) -> np.ndarray:
    return np.asarray(x, dtype=np.uint64) & _M32


def fmix32(x) -> np.ndarray:
    x = _u32(x)
    x ^= x >> np.uint64(16)
    x = (x * np.uint64(0x85EBCA6B)) & _M32
    x ^= x >> np.uint64(13)
    x = (x * np.uint64(0xC2B2AE35)) & _M32
    x ^= x >> np.uint64(16)
    return x


def _rotl(x: np.ndarray, k: int) -> np.ndarray:
    return ((x << np.uint64(k)) | (x >> np.uint64(32 - k))) & _M32


def init_states(seed: int, sims: np.ndarray, stream: int) -> np.ndarray:
    """State array (n, 4) of uint64 holding 32-bit words."""
    sims = _u32(sims)
    key = fmix32(fmix32(np.uint64(seed & 0xFFFFFFFF) ^ np.uint64(0x243F6A88)) ^ np.uint64(stream)) ^ sims
    out = np.empty((len(sims), 4), dtype=np.uint64)
    s = key.copy()
    for i in range(4):
        s = (s + np.uint64(0x9E3779B9)) & _M32
        out[:, i] = fmix32(s)
    zero = (out == 0).all(axis=1)
    out[zero, 0] = 1
    return out


def next_u32(state: np.ndarray, rows: np.ndarray | None = None) -> np.ndarray:
    """Advance the selected rows (all if None) in place and return their outputs."""
    st = state if rows is None else state[rows]
    s0, s1, s2, s3 = st[:, 0].copy(), st[:, 1].copy(), st[:, 2].copy(), st[:, 3].copy()
    result = (_rotl((s1 * np.uint64(5)) & _M32, 7) * np.uint64(9)) & _M32
    t = (s1 << np.uint64(9)) & _M32
    s2 ^= s0
    s3 ^= s1
    s1 ^= s2
    s0 ^= s3
    s2 ^= t
    s3 = _rotl(s3, 11)
    new = np.stack([s0, s1, s2, s3], axis=1)
    if rows is None:
        state[:] = new
    else:
        state[rows] = new
    return result


def uniforms(state: np.ndarray, k: int, rows: np.ndarray | None = None) -> np.ndarray:
    """k uniforms in [0, 1) per selected row, shape (n, k): u = x * 2**-32."""
    return np.stack([next_u32(state, rows).astype(np.float64) * 2.0**-32 for _ in range(k)], axis=1)


def categorical(u: np.ndarray, eta: np.ndarray) -> np.ndarray:
    """First class k with u * cum[-1] < cum[k], cum the running sum of exp(eta - max)."""
    cum = np.cumsum(np.exp(eta - eta.max(axis=1, keepdims=True)), axis=1)
    hit = (u[:, None] * cum[:, -1:]) < cum
    k = np.argmax(hit, axis=1)
    k[~hit.any(axis=1)] = eta.shape[1] - 1
    return k


def normal_pair(u1: np.ndarray, u2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Box-Muller using log(1 - u) so u = 0 is safe."""
    r = np.sqrt(-2.0 * np.log(1.0 - u1))
    return r * np.cos(2 * np.pi * u2), r * np.sin(2 * np.pi * u2)


def known_answers() -> dict:
    """Known-answer vectors written to tests/data/cricket_parity/prng_kat.json."""
    cases = []
    for seed, stream in ((0, 0), (1, 0), (123456789, 3), (0xFFFFFFFF, 4)):
        sims = np.array([0, 1, 2, 1000, 2**31 - 1])
        st = init_states(seed, sims, stream)
        outs = np.stack([next_u32(st) for _ in range(8)], axis=1)
        cases.append({"seed": seed, "stream": stream, "sims": sims.tolist(),
                      "outputs": outs.astype(np.int64).tolist()})
    return {"fmix32": {str(x): int(fmix32(x)) for x in (0, 1, 0x243F6A88, 0xDEADBEEF, 0xFFFFFFFF)},
            "cases": cases}


_M = 0xFFFFFFFF
_INV32 = 2.0**-32


def fmix32_int(x: int) -> int:
    """Scalar murmur3 finalizer on a Python int (same output as fmix32)."""
    x &= _M
    x ^= x >> 16
    x = (x * 0x85EBCA6B) & _M
    x ^= x >> 13
    x = (x * 0xC2B2AE35) & _M
    return x ^ (x >> 16)


class Stream:
    """Scalar twin of ``Stream`` in rng.js: one (seed, sim, stream) generator on Python ints."""
    __slots__ = ("s",)

    def __init__(self, seed: int, sim: int, stream: int):
        key = (fmix32_int(fmix32_int((seed ^ 0x243F6A88) & _M) ^ stream) ^ sim) & _M
        s = []
        for _ in range(4):
            key = (key + 0x9E3779B9) & _M
            s.append(fmix32_int(key))
        if not any(s):
            s[0] = 1
        self.s = s

    def next_u32(self) -> int:
        return self.next_block(1)[0]

    def next_block(self, k: int) -> list[int]:
        s0, s1, s2, s3 = self.s
        out = []
        for _ in range(k):
            x = (s1 * 5) & _M
            out.append(((((x << 7) | (x >> 25)) & _M) * 9) & _M)
            t = (s1 << 9) & _M
            s2 ^= s0
            s3 ^= s1
            s1 ^= s2
            s0 ^= s3
            s2 ^= t
            s3 = ((s3 << 11) | (s3 >> 21)) & _M
        self.s = [s0, s1, s2, s3]
        return out

    def uniforms(self, k: int) -> list[float]:
        """k uniforms u = x * 2**-32, exactly as rng.js."""
        return [x * _INV32 for x in self.next_block(k)]
