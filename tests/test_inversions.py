import random
import shutil
import tempfile
import unittest
from pathlib import Path

from workbench.judge import Judge
from tools.array_cases import count_inversions, generated_cases
from support import copy_problem
from workbench.repository import Repository, TEMPLATE

ROOT = Path(__file__).resolve().parent.parent
PROBLEM = "逆序对的数量"

# An independent merge-based solution, used only in temporary test workspaces.
SOLUTION = r'''
#include <iostream>
#include <vector>
using Count = long long;
std::vector<int> values, buffer;
Count solve(int l, int r) {
    if (l >= r) return 0;
    int mid = (l + r) / 2;
    Count count = solve(l, mid) + solve(mid + 1, r);
    int i = l, j = mid + 1, k = l;
    while (i <= mid && j <= r) {
        if (values[i] <= values[j]) buffer[k++] = values[i++];
        else { count += mid - i + 1; buffer[k++] = values[j++]; }
    }
    while (i <= mid) buffer[k++] = values[i++];
    while (j <= r) buffer[k++] = values[j++];
    for (int p = l; p <= r; p++) values[p] = buffer[p];
    return count;
}
int main() {
    int n; std::cin >> n;
    values.resize(n); buffer.resize(n);
    for (int &value : values) std::cin >> value;
    std::cout << solve(0, n - 1) << '\n';
}
'''


class InversionsTest(unittest.TestCase):
    def test_oracle_matches_brute_force_and_does_not_modify_input(self):
        rng = random.Random(788)
        arrays = [[1], [2, 1], [2, 2], [2, 3, 4, 5, 6, 1], [2, 1, 2, 1]]
        arrays += [[rng.randint(1, 9) for _ in range(rng.randint(1, 50))] for _ in range(100)]
        for values in arrays:
            original = values[:]
            expected = sum(values[i] > values[j] for i in range(len(values)) for j in range(i + 1, len(values)))
            self.assertEqual(count_inversions(values), expected, values)
            self.assertEqual(values, original)

    def test_cases_are_reproducible_and_include_strict_comparison_and_overflow(self):
        cases = generated_cases("inversions", 788)
        self.assertEqual(cases, generated_cases("inversions", 788))
        outputs = {case["name"]: int(case["output"]) for case in cases}
        self.assertEqual(outputs["十万元素完全逆序"], 4_999_950_000)
        self.assertEqual(outputs["十万相同元素"], 0)
        self.assertEqual(outputs["两个相等元素"], 0)
        self.assertEqual(outputs["相等值跨左右区间"], 3)
        for case in cases:
            lines = case["input"].splitlines()
            n = int(lines[0])
            values = list(map(int, lines[1].split()))
            self.assertEqual(n, len(values))
            self.assertTrue(1 <= n <= 100_000)
            self.assertTrue(all(1 <= value <= 10**9 for value in values))
            if n <= 500:
                expected = sum(values[i] > values[j] for i in range(n) for j in range(i + 1, n))
                self.assertEqual(int(case["output"]), expected, case["name"])

    def test_new_problem_starts_blank_and_judges_correct_and_incorrect_solutions(self):
        with tempfile.TemporaryDirectory(prefix="acwing-inversions-") as directory:
            root = Path(directory)
            copy_problem(root, PROBLEM)
            repo = Repository(root)
            self.assertEqual(repo.list_problems()[0]["id"], PROBLEM)
            self.assertIsNone(repo.detail(PROBLEM)["attempt"])
            self.assertEqual(repo.create_attempt(PROBLEM)["source"], TEMPLATE)
            judge = Judge(repo)

            attempt = repo.create_attempt(PROBLEM, SOLUTION)
            sample = judge.run(PROBLEM, attempt["id"], attempt["revision"], "sample")
            self.assertEqual(sample["status"], "PASS", sample)
            self.assertEqual(sample["cases"][0]["stdout"].strip(), "5")
            result = judge.run(PROBLEM, attempt["id"], attempt["revision"], "check")
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["passed"], 33)
            self.assertEqual(result["passed"], result["total"])

            for wrong in (SOLUTION.replace("using Count = long long", "using Count = int"),
                          SOLUTION.replace("values[i] <= values[j]", "values[i] < values[j]")):
                attempt = repo.create_attempt(PROBLEM, wrong)
                result = judge.run(PROBLEM, attempt["id"], attempt["revision"], "check")
                self.assertEqual(result["status"], "WA", result)


if __name__ == "__main__":
    unittest.main()
