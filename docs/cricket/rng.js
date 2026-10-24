// xoshiro128** with splitmix32 stream seeding; bit-for-bit twin of beating/cricket/rng.py.
// See CRICKET-MODEL-PLAN.md section 9.5.

export const STREAMS = { ball: 0, over: 1, innings: 2, match: 3, player: 4 };
export const SLOTS = { ball: 12, over: 4, innings: 4, match: 64, player: 4 };

export function fmix32(x) {
  x >>>= 0;
  x ^= x >>> 16; x = Math.imul(x, 0x85EBCA6B) >>> 0;
  x ^= x >>> 13; x = Math.imul(x, 0xC2B2AE35) >>> 0;
  x ^= x >>> 16;
  return x >>> 0;
}

const rotl = (x, k) => ((x << k) | (x >>> (32 - k))) >>> 0;

export class Stream {
  constructor(seed, sim, stream) {
    const key = (fmix32(fmix32((seed ^ 0x243F6A88) >>> 0) ^ stream) ^ sim) >>> 0;
    this.s = new Uint32Array(4);
    let sm = key;
    for (let i = 0; i < 4; i++) {
      sm = (sm + 0x9E3779B9) >>> 0;
      this.s[i] = fmix32(sm);
    }
    if (!this.s[0] && !this.s[1] && !this.s[2] && !this.s[3]) this.s[0] = 1;
  }

  nextU32() {
    const s = this.s;
    const result = Math.imul(rotl(Math.imul(s[1], 5) >>> 0, 7), 9) >>> 0;
    const t = (s[1] << 9) >>> 0;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t;
    s[3] = rotl(s[3], 11);
    return result;
  }

  // Fill `out` (Float64Array) with k uniforms in [0, 1).
  uniforms(k, out) {
    for (let i = 0; i < k; i++) out[i] = this.nextU32() * 2.3283064365386963e-10;
    return out;
  }
}

// First class k with u * cum[last] < cum[k], cum the running sum of exp(eta - max).
export function categorical(u, eta, n, scratch) {
  let mx = -Infinity;
  for (let k = 0; k < n; k++) if (eta[k] > mx) mx = eta[k];
  let c = 0;
  for (let k = 0; k < n; k++) { c += Math.exp(eta[k] - mx); scratch[k] = c; }
  const target = u * c;
  for (let k = 0; k < n; k++) if (target < scratch[k]) return k;
  return n - 1;
}

export function normalPair(u1, u2) {
  const r = Math.sqrt(-2 * Math.log(1 - u1));
  return [r * Math.cos(2 * Math.PI * u2), r * Math.sin(2 * Math.PI * u2)];
}
