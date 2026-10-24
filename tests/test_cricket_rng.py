import json
from pathlib import Path
import shutil
import subprocess
import unittest

import numpy as np

from beating.cricket import rng

ROOT = Path(__file__).resolve().parents[1]
KAT = ROOT / "tests" / "data" / "cricket_parity" / "prng_kat.json"


class RngTests(unittest.TestCase):
    def test_python_matches_known_answers(self):
        self.assertEqual(rng.known_answers(), json.loads(KAT.read_text()))

    def test_states_are_distinct_and_streams_independent(self):
        st = rng.init_states(7, np.arange(50_000), 0)
        self.assertEqual(len({tuple(r) for r in st.tolist()}), 50_000)
        other = rng.init_states(7, np.arange(50_000), 1)
        self.assertFalse((st == other).all(axis=1).any())

    def test_uniform_moments_and_categorical(self):
        st = rng.init_states(3, np.arange(200_000), 2)
        u = rng.uniforms(st, 2)
        self.assertAlmostEqual(u.mean(), 0.5, delta=0.003)
        eta = np.tile(np.log([0.2, 0.5, 0.3]), (len(u), 1))
        k = rng.categorical(u[:, 0], eta)
        np.testing.assert_allclose(np.bincount(k, minlength=3) / len(k), [0.2, 0.5, 0.3], atol=0.004)
        z1, z2 = rng.normal_pair(u[:, 0], u[:, 1])
        self.assertAlmostEqual(z1.std(), 1, delta=0.01)
        self.assertAlmostEqual(np.corrcoef(z1, z2)[0, 1], 0, delta=0.01)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_javascript_matches_known_answers(self):
        script = f"""
import {{ readFileSync }} from 'fs';
import {{ fmix32, Stream }} from '{(ROOT / "docs" / "cricket" / "rng.js").as_posix()}';
const kat = JSON.parse(readFileSync('{KAT.as_posix()}'));
let bad = 0;
for (const [x, v] of Object.entries(kat.fmix32)) if (fmix32(Number(x)) !== v) bad++;
for (const c of kat.cases) c.sims.forEach((sim, i) => {{
  const s = new Stream(c.seed >>> 0, sim, c.stream);
  for (let j = 0; j < 8; j++) if (s.nextU32() !== c.outputs[i][j]) bad++;
}});
process.stdout.write(String(bad));
"""
        out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout, "0")


if __name__ == "__main__":
    unittest.main()
