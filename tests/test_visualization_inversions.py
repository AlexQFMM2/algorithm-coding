import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workbench.visualization_protocol import validate_trace

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'visualizer/examples/inversions.cpp'


class InversionVisualizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='inversions-visualization-')
        cls.working = Path(cls.temporary.name)
        cls.binary = cls.working / 'demo'
        cls.source = SOURCE.read_text(encoding='utf-8')
        subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror=return-type',
                        '-I'+str(ROOT/'workbench/include'), '-I'+str(ROOT/'vendor'), str(SOURCE), '-o', str(cls.binary)],
                       check=True, capture_output=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_demo(self, incoming):
        trace = self.working / 'visualization.json'
        trace.unlink(missing_ok=True)
        result = subprocess.run([sys.executable, str(ROOT/'workbench/worker.py'), str(self.binary)],
                                input=incoming, text=True, capture_output=True, cwd=self.working, timeout=5)
        return result, json.loads(trace.read_text()) if trace.exists() else None

    def test_examples_random_inputs_and_counting_steps_match_brute_force(self):
        arrays = [[42], [1,2,3,4], [4,3,2,1], [2,2,2], [2,1,2,1], [10**9,1,10**9], [2,4,6,1,3,5], list(range(20,0,-1))]
        rng = random.Random(788)
        arrays += [[rng.randint(1,20) for _ in range(rng.randint(1,20))] for _ in range(35)]
        for values in arrays:
            with self.subTest(values=values):
                result, trace = self.run_demo(f'{len(values)}\n'+ ' '.join(map(str,values))+'\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = sum(values[i]>values[j] for i in range(len(values)) for j in range(i+1,len(values)))
                self.assertEqual(int(result.stdout),expected)
                self.assertGreater(validate_trace(trace,len(self.source.splitlines())),0)
                counted = 0
                for command in trace['commands']:
                    if command['method'] != 'delay':continue
                    line, meta=command['args']
                    if meta['kind']=='count':
                        self.assertEqual(meta['after']-meta['before'],len(meta['pairs']))
                        self.assertTrue(all(a>b for a,b in meta['pairs']))
                        self.assertIn('cnt += mid - ll + 1;',self.source.splitlines()[line-1])
                        counted += len(meta['pairs'])
                self.assertEqual(counted,expected)
                self.assertEqual(trace['commands'][-1]['args'][1]['kind'],'complete')
        result,trace=self.run_demo('6\n2 4 6 1 3 5\n')
        steps=[c['args'][1] for c in trace['commands'] if c['method']=='delay']
        self.assertTrue(any(s['kind']=='count' and s['pairs']==[[2,1],[4,1],[6,1]] and s['after']-s['before']==3 for s in steps))
        self.assertTrue(any(s['kind']=='write_back' and '不用清零' in s['message'] for s in steps))

    def test_invalid_inputs_are_rejected_without_truncation_or_trace(self):
        for incoming in ['', '0\n', '21\n'+'1 '*21, '3\n1 2', '1\n0', '1\n1000000001', '1\n-1', '1\n1 extra', '1\n1.5', 'x\n1', '1\n'+'9'*30]:
            with self.subTest(incoming=incoming):
                result,trace=self.run_demo(incoming)
                self.assertEqual(result.returncode,2)
                self.assertTrue(result.stderr)
                self.assertIsNone(trace)


if __name__=='__main__':
    unittest.main()
